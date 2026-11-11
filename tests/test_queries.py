import copy
import json
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst import queries
from dotanalyst.db import Account, Base
from dotanalyst.steam import ANONYMOUS, store_match

TEMPLATE = json.loads((Path(__file__).parent / "fixtures" / "details_by_seq.json").read_text(encoding="utf-8"))[
    "result"
]["matches"][0]
SLOTS = [0, 1, 2, 3, 4, 128, 129, 130, 131, 132]
ME, FRIEND, STRANGER = 100, 200, 300


def make_match(match_id, day, radiant_win, accounts, game_mode=22, lobby_type=7) -> dict:
    """The recorded match with known heroes: slot 0-4 play heroes 1-5, slot 128-132 play heroes 6-10."""
    m = copy.deepcopy(TEMPLATE)
    m.update(
        match_id=match_id, match_seq_num=match_id, radiant_win=radiant_win, game_mode=game_mode,
        lobby_type=lobby_type, start_time=int(datetime(2026, *day, 12).timestamp()),
    )
    for player, slot, hero_id in zip(m["players"], SLOTS, range(1, 11)):
        player.update(player_slot=slot, hero_id=hero_id, account_id=accounts.get(slot, ANONYMOUS))
    return m


MATCHES = [
    make_match(1, (6, 10), True, {0: ME, 1: FRIEND, 4: STRANGER}),  # won, friend on my team
    make_match(2, (7, 10), True, {128: ME, 0: FRIEND}),  # lost, friend against me
    make_match(3, (8, 10), False, {0: ME, 2: FRIEND}, game_mode=23, lobby_type=0),  # lost, friend on my team
]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Account(account_id=ME), Account(account_id=FRIEND, label="friend")])
        s.add(Account(account_id=STRANGER, active=False))
        for m in MATCHES:
            store_match(s, m)
        s.commit()
        yield s


def ids(rows):
    return [r["match_id"] for r in rows]


def test_matches_newest_first_with_result(session):
    rows = queries.matches(session, queries.conditions(ME))
    assert ids(rows) == [3, 2, 1]
    assert [r["win"] for r in rows] == [0, 0, 1]
    assert [r["hero_id"] for r in rows] == [1, 6, 1]
    mine = MATCHES[0]["players"][0]
    assert (rows[2]["kills"], rows[2]["gold_per_min"]) == (mine["kills"], mine["gold_per_min"])
    assert rows[2]["items"][:6] == [mine[f"item_{i}"] for i in range(6)]


def test_filters(session):
    def found(**filters):
        return ids(queries.matches(session, queries.conditions(ME, **filters)))

    assert found(lobby_type=0) == [3]
    assert found(game_mode=22) == [2, 1]
    assert found(date_from=date(2026, 7, 1)) == [3, 2]
    assert found(date_to=date(2026, 7, 10)) == [2, 1]  # the end day is included
    assert found(date_from=date(2026, 7, 11), date_to=date(2026, 8, 9)) == []
    assert ids(queries.matches(session, queries.conditions(FRIEND))) == [3, 2, 1]


def test_heroes_counts_and_averages(session):
    rows = {r["hero_id"]: r for r in queries.heroes(session, queries.conditions(ME))}
    assert set(rows) == {1, 6}
    assert (rows[1]["games"], rows[1]["wins"]) == (2, 1)
    assert (rows[6]["games"], rows[6]["wins"]) == (1, 0)
    assert rows[1]["kills"] == TEMPLATE["players"][0]["kills"]  # same template player in both games
    assert rows[6]["gold_per_min"] == TEMPLATE["players"][5]["gold_per_min"]
    assert [r["hero_id"] for r in queries.heroes(session, queries.conditions(ME))] == [1, 6]  # most played first


def test_teammates_counts_only_same_team_and_tracked(session):
    rows = queries.teammates(session, queries.conditions(ME))
    assert rows == [{"account_id": FRIEND, "label": "friend", "games": 2, "wins": 1}]


def test_matchups_with_and_against(session):
    rows = {r["hero_id"]: r for r in queries.matchups(session, queries.conditions(ME))}
    # hero 2 sits in slot 1: my ally in matches 1 and 3, my enemy in match 2
    assert rows[2] == {"hero_id": 2, "with_games": 2, "with_wins": 1, "against_games": 1, "against_wins": 0}
    # hero 6 sits in slot 128: my enemy in matches 1 and 3; in match 2 it is me, which does not count
    assert rows[6] == {"hero_id": 6, "with_games": 0, "with_wins": 0, "against_games": 2, "against_wins": 1}
    assert rows[1] == {"hero_id": 1, "with_games": 0, "with_wins": 0, "against_games": 1, "against_wins": 0}
    assert len(rows) == 10
