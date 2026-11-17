"""Expected values were read by hand from the fixture replay's raw events, not produced by the code under test."""
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from dotanalyst import queries
from dotanalyst.db import (
    AbilityUpgrade, Base, Building, Death, Derived, Lane, Match, PlayerMinute, Purchase, Teamfight, TeamfightPlayer, Tormentor, Ward,
    WisdomRune,
)  # fmt: skip
from dotanalyst.derive import TABLES, Log, derive, fights, positions, read_log, recompute, tormentors, zone

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
    # damage is the replay's own running count; healing is every heal of another hero of the team up to that minute,
    # added up from the combat log. By 10:00 that was one heal: Dawnbreaker's 14 on Lich at 8:57
    assert [(ten[slot]["hero_damage"], ten[slot]["healing"]) for slot in (DAWNBREAKER, PHOENIX, MUERTA)] == [
        (2707, 14), (4195, 0), (7477, 0),
    ]  # fmt: skip
    fifteen = {r["player_slot"]: r for r in rows[PlayerMinute] if r["minute"] == 15}
    # Muerta healed only herself (6,812 of regeneration), which does not count. Dawnbreaker healed Lich for 194,
    # Phoenix for 92 and Luna for 135; Legion Commander (slot 4) healed Dawnbreaker twelve times for 24
    assert (fifteen[MUERTA]["hero_damage"], fifteen[MUERTA]["healing"]) == (10667, 0)
    assert [fifteen[slot]["healing"] for slot in (DAWNBREAKER, 4, PHOENIX)] == [421, 288, 28]


def test_stacks_pulls_and_lotuses(rows):
    at = {(r["player_slot"], r["minute"]): r for r in rows[PlayerMinute]}
    assert [at[slot, 10]["camps_stacked"] for slot in (DAWNBREAKER, 1, PHOENIX)] == [0, 1, 6]  # the replay's own count
    # Pulls. Dire's creeps killed kobolds at 2:35, a second after Rubick (slot 129) hit them. Radiant's creeps and
    # the kobolds killed each other from 2:41 to 3:04, Phoenix having hit the camp at 2:30; at 3:40 they killed a
    # creep of the next camp, which Legion Commander (slot 4) was fighting. Muerta pulled at 4:35
    assert [at[PHOENIX, minute]["camps_pulled"] for minute in (2, 3, 10)] == [0, 1, 1]
    assert [at[slot, 10]["camps_pulled"] for slot in (4, 129, MUERTA, 130, 2)] == [1, 1, 1, 0, 0]
    # Lotuses collected. Legion Commander (slot 4) stood at the top pool when its lotuses of 3:00, 9:00 and 12:00
    # were there (from 2:56, 9:25 and 12:30) and ate one at 3:02, 11:53 and 12:54. Muerta took the one of 6:00 at 6:10
    assert [at[4, minute]["lotuses"] for minute in (2, 3, 9, 10, 12, 13, 15)] == [0, 1, 1, 2, 2, 3, 3]
    assert (at[MUERTA, 6]["lotuses"], at[MUERTA, 7]["lotuses"], at[DAWNBREAKER, 15]["lotuses"]) == (0, 1, 0)
    # the bottom pool at 3:00: Lich (slot 2) stood on it and Luna (slot 1) 3 cells away. Luna ate that lotus at 5:56;
    # whether she took it or was handed it the replay does not say, so it counts for the hero on the pool
    assert (at[2, 3]["lotuses"], at[1, 15]["lotuses"]) == (1, 0)
    assert sum(at[slot, 15]["lotuses"] for slot in (0, 1, 2, 3, 4, 128, 129, 130, 131, 132)) == 6


def test_purchases(rows):
    luna = [(r["time"], r["item"]) for r in rows[Purchase] if r["player_slot"] == 1]
    assert luna[:2] == [(-89, "magic_stick"), (-89, "tango")]
    assert (485, "power_treads") in luna
    assert all(r["built_at"] is None for r in rows[Purchase])  # nothing is known about recipes here


def test_parts_built_into_a_bigger_item():
    recipes = {
        "power_treads": ["boots", "gloves", "belt_of_strength"], "magic_wand": ["magic_stick", "branches", "branches"],
        "maelstrom": ["mithril_hammer", "javelin", "gloves"],
    }  # fmt: skip
    bought = derive(read_log(FIXTURES / f"{MATCH_ID}.jsonl.gz"), recipes)[Purchase]
    luna = [(r["time"], r["item"], r["built_at"]) for r in bought if r["player_slot"] == 1]
    # wand at 3:30 from the stick and both branches of the start; treads at 8:05, with the Band of Elvenskin
    # (boots_of_elves) in the place of the recipe's Belt of Strength
    assert [r for r in luna if r[2] is not None] == [
        (-89, "magic_stick", 210), (-89, "branches", 210), (-89, "branches", 210),
        (168, "boots_of_elves", 485), (331, "boots", 485), (407, "gloves", 485),
    ]  # fmt: skip
    assert (-89, "quelling_blade", None) in luna and (485, "power_treads", None) in luna
    # Muerta bought gloves twice: the pair of 1:47 went into the treads at 3:55, the pair of 10:41 into Maelstrom
    muerta = [(r["time"], r["built_at"]) for r in bought if r["player_slot"] == MUERTA and r["item"] == "gloves"]
    assert muerta == [(107, 235), (641, 827)]


def test_skill_points(rows):
    spent = [(r["player_slot"], r["time"], r["ability"], r["level"], r["hero_level"]) for r in rows[AbilityUpgrade]]
    # Luna (slot 1): Lunar Blessing, innate and listed at level 1 when she appeared at -1:29, is not a point spent
    assert [r[1:] for r in spent if r[0] == 1] == [
        (-49, "luna_lucent_beam", 1, 1), (106, "luna_moon_glaive", 1, 2), (228, "luna_lucent_beam", 2, 3),
        (400, "luna_moon_glaive", 2, 4), (519, "luna_moon_glaive", 3, 5), (692, "luna_eclipse", 1, 6),
        (795, "luna_moon_glaive", 4, 7),
    ]  # fmt: skip
    # a talent: Muerta's at level 10, four seconds before she put the level's point into The Calling
    assert (MUERTA, 620, "special_bonus_attack_speed_20", 1, 10) in spent
    assert (MUERTA, 624, "muerta_the_calling", 1, 10) in spent
    # Shadow Fiend's three Shadowrazes level together and are one point: 14 points by level 13, a talent among them
    fiend = [r for r in spent if r[0] == SHADOW_FIEND]
    assert len(fiend) == 14 and fiend[0][1:] == (-81, "nevermore_shadowraze1", 1, 1)
    assert [r[2] for r in fiend if r[1] == 108] == ["nevermore_shadowraze1"]


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


def test_teamfight_healing_and_gains(rows):
    fight = {(p["n"], p["player_slot"]): p for p in rows[TeamfightPlayer]}
    # first fight, 6:18 to 6:50: every heal was a hero healing itself (Muerta 593), so nobody healed anyone
    assert [fight[0, slot]["healing"] for slot in (MUERTA, 130, 4, 2, DAWNBREAKER, 1)] == [0, 0, 0, 0, 0, 0]
    # net worth and experience at 6:50 minus at 6:18; Lich (slot 2) died in it, Pangolier (131) was not near
    assert (fight[0, MUERTA]["net_worth_gain"], fight[0, MUERTA]["xp_gain"]) == (489, 454)
    assert (fight[0, 2]["net_worth_gain"], fight[0, 131]["xp_gain"]) == (39, 0)
    # last fight: Dawnbreaker healed Luna for 135 (and itself for 205, not counted); Phoenix healed Luna for 28
    assert (fight[4, DAWNBREAKER]["healing"], fight[4, PHOENIX]["healing"]) == (135, 28)
    assert (fight[4, 131]["net_worth_gain"], fight[4, 131]["xp_gain"]) == (930, 1487)


def test_wards(rows):
    assert Counter(w["type"] for w in rows[Ward]) == {"obs": 17, "sen": 24}
    expired, dewarded = rows[Ward][0], rows[Ward][1]
    assert (expired["player_slot"], expired["placed"], expired["removed"], expired["killed"]) == (0, -60, 300, False)
    assert (dewarded["player_slot"], dewarded["placed"], dewarded["removed"]) == (SHADOW_FIEND, -56, -43)
    assert (dewarded["killed"], dewarded["killed_by"]) == (True, PHOENIX)


def test_buildings(rows):
    # Dire took three towers and the Ancient; creeps and the filler buildings of the base are not in it
    assert rows[Building] == [
        {"name": "goodguys_tower1_mid", "time": 508},
        {"name": "goodguys_tower1_bot", "time": 611},
        {"name": "goodguys_tower1_top", "time": 806},
        {"name": "goodguys_fort", "time": 911},
    ]


def test_positions():
    """The 20 seconds before Phoenix's first death at 1:40."""
    found = positions(FIXTURES / "8810606282.jsonl.gz", 80, 100)
    assert len(found) == 210  # ten heroes, 21 seconds
    at = {(p["time"], p["player_slot"]): p for p in found}
    assert at[80, PHOENIX] == {"time": 80, "player_slot": PHOENIX, "x": 88.228516, "y": 163.85059, "alive": True}
    assert (at[100, PHOENIX]["x"], at[100, PHOENIX]["y"]) == (83.84253, 164.08154)
    assert (at[100, SHADOW_FIEND]["x"], at[100, SHADOW_FIEND]["y"]) == (126.23926, 129.03516)


def test_zone():
    assert zone(128, 128) == "mid"
    assert zone(80, 150) == "top" and zone(120, 175) == "top"
    assert zone(150, 80) == "bot" and zone(176, 120) == "bot"
    assert zone(110, 140) == "jungle"
    assert zone(74, 78) is None  # Radiant fountain


def test_lanes(rows):
    lane = {r["player_slot"]: r["lane"] for r in rows[Lane]}
    assert (lane[DAWNBREAKER], lane[SHADOW_FIEND], lane[PHOENIX], lane[MUERTA]) == ("mid", "mid", "top", "top")
    for team in (range(0, 5), range(128, 133)):
        assert Counter(lane[slot] for slot in team) == {"top": 2, "mid": 1, "bot": 2}


def test_wisdom_runes(rows):
    """The game ended at 15:11: two spawns. Muerta (Dire) took Radiant's rune at 7:03 with Phoenix standing by."""
    found = {(r["time"], r["rune"]): r for r in rows[WisdomRune]}
    assert set(found) == {(420, "radiant"), (420, "dire"), (840, "radiant"), (840, "dire")}
    lead = {"radiant_lead": -4601}
    assert found[420, "radiant"] == {"time": 420, "rune": "radiant", "radiant_heroes": 1, "dire_heroes": 1, "taken_by_radiant": False, **lead}
    assert found[420, "dire"] == {"time": 420, "rune": "dire", "radiant_heroes": 1, "dire_heroes": 1, "taken_by_radiant": False, **lead}
    lead = {"radiant_lead": -11765}
    assert found[840, "radiant"] == {"time": 840, "rune": "radiant", "radiant_heroes": 1, "dire_heroes": 0, "taken_by_radiant": True, **lead}
    assert found[840, "dire"] == {"time": 840, "rune": "dire", "radiant_heroes": 0, "dire_heroes": 0, "taken_by_radiant": None, **lead}


def test_tormentors():
    """The fixture has none: a made-up log of two heroes a side, with the Dire hero in slot 2 dead at 25:00."""
    events = [{"type": "player_slot", "key": str(k), "value": v} for k, v in enumerate((0, 1, 128, 129))]
    for slot, (networth, life) in enumerate(((5000, 0), (4000, 0), (3000, 1), (2500, 0))):
        events.append({"type": "interval", "time": 1500, "slot": slot, "networth": networth, "life_state": life})
    events += [
        {"type": "CHAT_MESSAGE_MINIBOSS_KILL", "time": 1500, "value": 2, "player1": 0},
        {"type": "CHAT_MESSAGE_MINIBOSS_KILL", "time": 1500, "value": 3, "player1": -1},  # a summon's blow
    ]
    assert tormentors(Log(events)) == [
        {"time": 1500, "radiant": True, "enemies_dead": 1, "radiant_lead": 3500},
        {"time": 1500, "radiant": False, "enemies_dead": 0, "radiant_lead": 3500},
    ]


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
        assert all(n for model, n in zip(TABLES, first) if model is not Tormentor)  # the game ended before 20:00
        recompute(session, FIXTURES)
        assert counts() == first

        found = queries.match(session, MATCH_ID)
        assert len({r["player_slot"] for r in found["player_minute"]}) == 10
        assert len(found["deaths"]) == 37 and len(found["teamfights"]) == 5 and len(found["lanes"]) == 10
        assert queries.match(session, 2)["player_minute"] == []
        assert queries.match(session, 3) is None
