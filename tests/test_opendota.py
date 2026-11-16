import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from dotanalyst import opendota
from dotanalyst.db import Base, Derived, PlayerGame, PlayerGameList
from dotanalyst.opendota import fetch_player_games, unlisted_players
from dotanalyst.steam import ANONYMOUS, store_league_match

FIXTURES = Path(__file__).parent / "fixtures"
GAMES = (FIXTURES / "opendota_player_matches.json").read_bytes()  # made up, as OpenDota sends them for player 1001
PLAYER = 1001


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def league_game(session: Session, match_id: int, start_time: int, accounts: dict[int, int] = {}) -> None:
    """The recorded league game; `accounts` gives some of its players (by index) other account ids."""
    game = json.loads((FIXTURES / "league_details.json").read_text(encoding="utf-8"))["result"]["matches"][0]
    game.update(match_id=match_id, start_time=start_time)
    for i, account_id in accounts.items():
        game["players"][i]["account_id"] = account_id
    store_league_match(session, game)
    session.commit()


def opendota_sends(calls: list[httpx.Request], status=200, body=GAMES) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_players_games_outside_the_league_are_stored_once(session):
    league_game(session, 2003, start_time=1763150000)  # in OpenDota's list too, as a ranked game
    calls = []
    assert fetch_player_games(session, opendota_sends(calls), PLAYER) == 4
    assert calls[0].url.path == f"/api/players/{PLAYER}/matches"
    assert calls[0].url.params["limit"] == str(opendota.ASKED) and "lane_role" in calls[0].url.params.get_list("project")
    games = {g.match_id: g for g in session.scalars(select(PlayerGame))}
    # 2005 and 2004 are lobby games (practice, tournament), 2003 is a stored league game, 2002 has a string id
    assert sorted(games) == [2001, 2006, 2007, 2008]
    assert (games[2006].lane_role, games[2006].kills, games[2001].game_mode) == (None, 5, 23)
    assert session.get(PlayerGameList, PLAYER) is not None
    assert fetch_player_games(session, opendota_sends(calls), PLAYER) == 0
    assert len(calls) == 1  # a listed player is never asked for again


def test_no_more_than_the_last_hundred_games_are_kept(session, monkeypatch):
    monkeypatch.setattr(opendota, "GAMES", 2)
    assert fetch_player_games(session, opendota_sends([]), PLAYER) == 2
    assert sorted(session.scalars(select(PlayerGame.match_id))) == [2007, 2008]  # OpenDota sends the newest first


def test_a_player_who_hides_their_games_is_listed_without_games(session):
    assert fetch_player_games(session, opendota_sends([], body=b"[]"), PLAYER) == 0
    assert session.get(PlayerGameList, PLAYER) is not None


@pytest.mark.parametrize("status, body", [(500, b""), (200, b'{"error": "rate limit"}')])
def test_a_failed_answer_leaves_the_player_unlisted(session, status, body):
    with pytest.raises(httpx.HTTPError):
        fetch_player_games(session, opendota_sends([], status, body), PLAYER)
    assert session.get(PlayerGameList, PLAYER) is None


def test_refresh_asks_at_once_for_the_players_never_asked_for(session, monkeypatch):
    from dotanalyst import poll

    calls = []
    client = opendota_sends(calls)
    monkeypatch.setattr(poll.httpx, "Client", lambda: client)
    session.add(PlayerGameList(account_id=PLAYER, fetched_at=0))
    session.commit()
    assert poll.refresh_players(session.get_bind(), [PLAYER, 1002]) == 1
    assert [c.url.path for c in calls] == ["/api/players/1002/matches"]
    assert session.get(PlayerGameList, 1002) is not None


def test_unlisted_players_come_from_the_newest_league_games(session):
    # the fixture's players are 1001 to 1010; in the newer game the first is anonymous and the second is 3001
    league_game(session, 1, start_time=1763000000)
    league_game(session, 2, start_time=1763100000, accounts={0: ANONYMOUS, 1: 3001})
    session.add(PlayerGameList(account_id=1003, fetched_at=0))
    session.commit()
    assert unlisted_players(session, 3) == [3001, 1004, 1005]  # anonymous and listed players are left out
    assert unlisted_players(session, 50) == [3001, *range(1004, 1011), 1001, 1002]  # each player once
