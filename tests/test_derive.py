"""Expected values were read by hand from the fixture replay's raw events, not produced by the code under test."""
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from dotanalyst import queries
from dotanalyst.db import Base, Death, Derived, Lane, Match, PlayerMinute, Purchase, Teamfight, TeamfightPlayer, Ward
from dotanalyst.derive import TABLES, derive, fights, read_log, recompute, zone

FIXTURES = Path(__file__).parent / "fixtures"
MATCH_ID = 8810606282
DAWNBREAKER, PHOENIX, MUERTA, SHADOW_FIEND = 0, 3, 128, 132  # player slots in the fixture


@pytest.fixture(scope="module")
def rows():
    return derive(read_log(FIXTURES / f"{MATCH_ID}.jsonl.gz"))


def test_per_minute_numbers(rows):
    ten = {r["player_slot"]: r for r in rows[PlayerMinute] if r["minute"] == 10}
    assert len(ten) == 10
    assert (ten[DAWNBREAKER]["last_hits"], ten[DAWNBREAKER]["net_worth"], ten[DAWNBREAKER]["xp"]) == (46, 3188, 3697)
    assert max(r["minute"] for r in rows[PlayerMinute]) == 15  # the game ended at 15:11


def test_stacks_and_lotuses(rows):
    at = {(r["player_slot"], r["minute"]): r for r in rows[PlayerMinute]}
    assert [at[slot, 10]["camps_stacked"] for slot in (DAWNBREAKER, 1, PHOENIX)] == [0, 1, 6]  # the replay's own count
    # Legion Commander (slot 4) ate a lotus at 3:02, 11:53 and 12:54, Luna (slot 1) one at 5:56, Dawnbreaker none
    assert [at[4, minute]["lotuses"] for minute in (3, 4, 10, 12, 13, 15)] == [0, 1, 1, 2, 3, 3]
    assert (at[1, 5]["lotuses"], at[1, 10]["lotuses"], at[DAWNBREAKER, 15]["lotuses"]) == (0, 1, 0)


def test_purchases(rows):
    luna = [(r["time"], r["item"]) for r in rows[Purchase] if r["player_slot"] == 1]
    assert luna[:2] == [(-89, "magic_stick"), (-89, "tango")]
    assert (485, "power_treads") in luna


def test_deaths_are_the_scoreboard_deaths(rows):
    assert len(rows[Death]) == 37
    first = rows[Death][0]
    assert (first["player_slot"], first["time"], first["killer_slot"]) == (PHOENIX, 100, MUERTA)
    assert (round(first["x"]), round(first["y"])) == (84, 164)  # top lane, where Phoenix was standing


def test_fight_grouping():
    assert fights([0, 10, 20]) == [(-15, 35, 3)]
    assert fights([100, 114, 129]) == []  # the third death comes 15 s after the second: too late
    assert fights([5, 6]) == []


def test_teamfights(rows):
    assert [(f["start"], f["end"], f["deaths"]) for f in rows[Teamfight]] == [
        (378, 410, 4), (519, 557, 3), (575, 627, 4), (662, 717, 4), (812, 863, 6),
    ]  # fmt: skip
    assert sum(d["in_teamfight"] for d in rows[Death]) == 4 + 3 + 4 + 4 + 6
    first = {p["player_slot"]: p for p in rows[TeamfightPlayer] if p["n"] == 0}
    assert len(first) == 10
    assert sum(p["deaths"] for p in first.values()) == 4
    assert first[PHOENIX]["took_part"] and first[PHOENIX]["deaths"] == 1 and first[PHOENIX]["damage"] > 0
    assert not first[DAWNBREAKER]["took_part"] and first[DAWNBREAKER]["damage"] == 0  # was mid, away from it


def test_wards(rows):
    assert Counter(w["type"] for w in rows[Ward]) == {"obs": 17, "sen": 24}
    expired, dewarded = rows[Ward][0], rows[Ward][1]
    assert (expired["player_slot"], expired["placed"], expired["removed"], expired["killed"]) == (0, -60, 300, False)
    assert (dewarded["player_slot"], dewarded["placed"], dewarded["removed"]) == (SHADOW_FIEND, -56, -43)
    assert (dewarded["killed"], dewarded["killed_by"]) == (True, PHOENIX)


def test_zone():
    assert zone(128, 128) == "mid"
    assert zone(80, 150) == "top" and zone(120, 175) == "top"
    assert zone(150, 80) == "bot" and zone(176, 120) == "bot"
    assert zone(110, 140) == "jungle"
    assert zone(74, 78) is None  # Radiant fountain


def test_lanes(rows):
    lane = {r["player_slot"]: r for r in rows[Lane]}
    assert (lane[DAWNBREAKER]["lane"], lane[DAWNBREAKER]["opponent_slot"]) == ("mid", SHADOW_FIEND)
    assert (lane[SHADOW_FIEND]["lane"], lane[SHADOW_FIEND]["opponent_slot"]) == ("mid", DAWNBREAKER)
    for team in (range(0, 5), range(128, 133)):
        assert Counter(lane[slot]["lane"] for slot in team) == {"top": 2, "mid": 1, "bot": 2}
    # two enemies share Phoenix's lane; the opponent is the one with more last hits at 10:00 (69 against 21)
    assert lane[PHOENIX]["opponent_slot"] == MUERTA


def test_recompute_is_repeatable_and_feeds_the_match_query():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    with Session(engine) as session:
        for match_id, state in ((MATCH_ID, "parsed"), (1, "parsed"), (2, "none")):  # match 1 has lost its raw log
            session.add(
                Match(
                    match_id=match_id, match_seq_num=1, start_time=0, duration=911, radiant_win=False,
                    game_mode=22, lobby_type=7, cluster=0, raw_json={}, replay_state=state,
                )
            )
        session.commit()

        def counts():
            return [session.scalar(select(func.count()).select_from(model)) for model in TABLES]

        done, problems = recompute(session, FIXTURES)
        assert done == 1 and len(problems) == 1 and "match 1" in problems[0]
        first = counts()
        assert all(first)
        recompute(session, FIXTURES)
        assert counts() == first

        found = queries.match(session, MATCH_ID)
        assert len({r["player_slot"] for r in found["player_minute"]}) == 10
        assert len(found["deaths"]) == 37 and len(found["teamfights"]) == 5 and len(found["lanes"]) == 10
        assert queries.match(session, 2)["player_minute"] == []
        assert queries.match(session, 3) is None
