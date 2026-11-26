"""Tournament stats from stored league games: heroes, players, standings and head-to-head."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst import league_page, league_stats, steam
from dotanalyst.db import Base, Derived, League, LeagueCatalog, LeagueMatch, PlayerName
from tests.test_league_page import NOW, client

HOUR = 3600


@pytest.fixture(autouse=True)
def no_steam_pause(monkeypatch):
    monkeypatch.setattr(steam, "PAUSE", 0)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(LeagueCatalog(league_id=1002, name="Pro Series 5", tier="professional", lp_checked=NOW))
        s.add(LeagueCatalog(league_id=1003, name="Friday Amateur League S9", tier="excluded", lp_checked=NOW))
        s.commit()
        yield s


def player(account_id, radiant=True, hero_id=1, kills=0, deaths=0, assists=0, **more) -> dict:
    return {"account_id": account_id, "player_slot": 0 if radiant else 128, "hero_id": hero_id, "kills": kills,
            "deaths": deaths, "assists": assists, "gold_per_min": 500, "xp_per_min": 600, "last_hits": 100,
            "hero_damage": 20000, **more}  # fmt: skip


def game(match_id, radiant=3001, dire=3002, radiant_win=True, players=(), picks_bans=None, league_id=1003, start=NOW,
         **raw) -> LeagueMatch:
    data = {"players": list(players), "radiant_score": 20, "dire_score": 5, **raw}
    if picks_bans is not None:
        data["picks_bans"] = picks_bans
    return LeagueMatch(match_id=match_id, league_id=league_id, start_time=start, radiant_team_id=radiant,
                       dire_team_id=dire, radiant_name=f"Team {radiant}", dire_name=f"Team {dire}",
                       radiant_win=radiant_win, raw_json=data)  # fmt: skip


def pick(hero_id, team, is_pick=True) -> dict:
    return {"hero_id": hero_id, "team": team, "is_pick": is_pick, "order": 0}


def test_heroes_count_picks_wins_bans_and_contested():
    rows = [
        game(9001, picks_bans=[pick(1, 0), pick(2, 1, is_pick=False)]),
        game(9002, radiant_win=False, picks_bans=[pick(1, 1)]),
    ]
    found = league_stats.heroes(rows)
    by_id = {h["hero_id"]: h for h in found}
    assert (by_id[1]["picks"], by_id[1]["wins"], by_id[1]["bans"], by_id[1]["contested"]) == (2, 2, 0, 1.0)
    assert (by_id[2]["picks"], by_id[2]["wins"], by_id[2]["bans"], by_id[2]["contested"]) == (0, 0, 1, 0.5)
    assert found[0]["hero_id"] == 1


def test_players_average_per_game_and_take_their_main_team():
    rows = [
        game(9001, players=[player(1001, hero_id=5, kills=10, deaths=2, assists=0)]),
        game(9002, players=[player(1001, hero_id=5, kills=0, deaths=2, assists=0)]),
        game(9003, radiant=3002, dire=3001, radiant_win=False,
             players=[player(1001, hero_id=7, kills=5, deaths=0, assists=3)]),  # for 3002 this once, and lost
    ]
    (p,) = league_stats.players(rows, {1001: ("Player 1", "https://example.invalid/a.png")})
    assert (p["games"], p["kills"], p["kda"], p["team_id"], p["name"]) == (3, 5.0, round(18 / 4, 2), 3001, "Player 1")
    assert p["heroes"][0] == 5 and p["wins"] == 2


def test_anonymous_players_and_games_without_drafts():
    rows = [
        game(9001, players=[player(steam.ANONYMOUS), player(1001)]),  # no picks_bans: an all-pick lobby
        game(9002, players=[player(1001)], picks_bans=[pick(3, 0)]),
    ]
    assert [p["account_id"] for p in league_stats.players(rows, {})] == [1001]
    (h,) = league_stats.heroes(rows)
    assert (h["hero_id"], h["picks"], h["contested"]) == (3, 1, 1.0)


def test_standings_order_and_skip_unplayed():
    side = lambda i: {"team_id": i, "name": f"Team {i}"}  # noqa: E731
    series = [
        {"teams": [side(1), side(2)], "score": [2, 0]},
        {"teams": [side(2), side(3)], "score": [2, 1]},
        {"teams": [side(1), side(3)], "score": [0, 0]},  # not played yet
    ]
    rows = league_stats.standings(series)
    assert [r["team_id"] for r in rows] == [1, 2, 3]
    b = rows[1]
    assert (b["series_wins"], b["series_losses"], b["map_wins"], b["map_losses"]) == (1, 1, 2, 3)
    assert rows[2]["series_losses"] == 1 and rows[2]["series_wins"] == 0


def test_head_to_head_across_leagues(session):
    session.add_all([League(league_id=1001, name="Spring Cup"), League(league_id=1002, name="Pro Series 5")])
    session.add_all([
        game(9001, league_id=1001, start=NOW - 30 * 24 * HOUR),
        game(9002, league_id=1001, start=NOW - 30 * 24 * HOUR + HOUR, radiant=3002, dire=3001, radiant_win=False),
        game(9003, league_id=1002, start=NOW, radiant_win=False),
        game(9004, league_id=1002, start=NOW, radiant=3001, dire=3009),  # another opponent
    ])  # fmt: skip
    session.commit()
    found = league_stats.head_to_head(session, 3001, 3002)
    assert found["games"] == 3 and found["wins"] == [2, 1]
    assert [s["league_name"] for s in found["series"]] == ["Pro Series 5", "Spring Cup"]  # newest first
    assert found["series"][1]["score"] == [2, 0] and found["series"][0]["score"] == [0, 1]


def test_page_adds_stats_for_a_subscribed_league(session, tmp_path):
    session.add(League(league_id=1003, name="Friday Amateur League S9"))
    session.add(game(9001, players=[player(1001)], picks_bans=[pick(1, 0)]))
    session.add(PlayerName(account_id=1001, name="Player 1", avatar=""))
    session.commit()
    page = league_page.page(session, client([]), "key", 1003, tmp_path, NOW)
    assert page["heroes"][0]["hero_id"] == 1 and page["players"][0]["name"] == "Player 1"
    assert page["standings"][0]["team_id"] == 3001
    preview = league_page.page(session, client([]), "key", 1002, tmp_path, NOW)
    assert preview["standings"] and "heroes" not in preview


def test_played_rosters_by_team():
    rows = [
        game(9001, players=[player(1001), player(1002), player(steam.ANONYMOUS)]),
        game(9002, players=[player(1002), player(1003, radiant=False)]),
    ]
    found = league_stats.played_rosters(rows, {1002: ("Player 2", None)})
    assert [p["account_id"] for p in found[3001]] == [1002, 1001]  # most games first
    assert found[3001][0]["name"] == "Player 2" and found[3001][0]["games"] == 2
    assert [p["account_id"] for p in found[3002]] == [1003]


def test_stored_teams_get_their_steam_logo(session, tmp_path):
    (tmp_path / "logos.json").write_text('{"77": "https://example.invalid/77.png"}')
    session.add(League(league_id=1003, name="Friday Amateur League S9"))
    session.add(game(9001, players=[player(1001)], radiant_logo=77, dire_logo=0))
    session.commit()
    asked = []
    page = league_page.page(session, client(asked), "key", 1003, tmp_path, NOW)
    logos = {t["team_id"]: t["logo"] for t in page["teams"]}
    assert logos == {3001: "https://example.invalid/77.png", 3002: None}
    assert not any("GetUGCFileDetails" in r.url.path for r in asked)  # from data/logos.json
    assert page["rosters"]["3001"][0]["account_id"] == 1001
