"""Expected values were worked out by hand from the fixture replay's raw events (see the notes on each test)."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from dotanalyst import metrics, queries
from dotanalyst.db import Account, Base, Derived, Match, MatchPlayer, Metric
from dotanalyst.derive import derive_match

FIXTURES = Path(__file__).parent / "fixtures"
MATCH_ID = 8810606282
DAWNBREAKER, LUNA, LICH, PHOENIX, SHADOW_FIEND = 0, 1, 2, 3, 132
ME = 100
# kills and assists as the replay's last scoreboard shows them; Radiant has 8 kills in total, Dire 28
SCOREBOARD = {0: (2, 1), 1: (1, 0), 2: (1, 4), 3: (3, 3), 4: (1, 3), 128: (4, 7), 129: (3, 11), 130: (3, 7), 131: (9, 4), 132: (9, 2)}  # fmt: skip


@pytest.fixture(scope="module")
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(account_id=ME))
        for match_id, state in ((MATCH_ID, "parsed"), (7, "none")):
            s.add(
                Match(
                    match_id=match_id, match_seq_num=1, start_time=match_id, duration=911, radiant_win=False,
                    game_mode=22, lobby_type=7, cluster=0, raw_json={}, replay_state=state,
                )
            )
            for slot, (kills, assists) in SCOREBOARD.items():
                s.add(
                    MatchPlayer(
                        match_id=match_id, player_slot=slot, hero_id=1, items=[], kills=kills, assists=assists,
                        account_id=ME if slot == DAWNBREAKER else None,
                    )
                )
        s.commit()
        derive_match(s, MATCH_ID, FIXTURES)
        yield s


@pytest.fixture(scope="module")
def match(session):
    return queries.match(session, MATCH_ID)


def test_lane_differences(match):
    # at 10:00 Dawnbreaker had 46 last hits and 3188 net worth, her mid opponent Shadow Fiend 93 and 5882
    assert metrics.lane_cs_diff(match, DAWNBREAKER) == 46 - 93
    assert metrics.lane_nw_diff(match, DAWNBREAKER) == 3188 - 5882
    assert metrics.lane_cs_diff(match, SHADOW_FIEND) == 93 - 46
    assert metrics.lane_cs_diff(match, PHOENIX) == 14 - 69  # against Muerta


def test_wards_placed(match):
    assert (metrics.obs_placed(match, DAWNBREAKER), metrics.sen_placed(match, DAWNBREAKER)) == (2, 0)
    assert (metrics.obs_placed(match, LICH), metrics.sen_placed(match, LICH)) == (3, 10)
    assert (metrics.obs_placed(match, LUNA), metrics.sen_placed(match, LUNA)) == (0, 1)


def test_wards_destroyed(match):
    # Phoenix: Shadow Fiend's observer at -0:43, Rubick's sentries at 1:02 and 1:09, Rubick's observer at 10:46;
    # the two wards "attacked" by Phoenix after the game were Phoenix's own, running out
    assert metrics.wards_destroyed(match, PHOENIX) == 4
    assert metrics.wards_destroyed(match, DAWNBREAKER) == 1  # Rubick's sentry at 13:15
    assert metrics.wards_destroyed(match, LUNA) == 0


def test_observer_lifetime(match):
    assert metrics.obs_lifetime(match, DAWNBREAKER) == (360 + 335) / 2  # one ran out, one was destroyed
    assert metrics.obs_lifetime(match, PHOENIX) == (135 + 360) / 2  # the third was still standing
    assert metrics.obs_lifetime(match, LUNA) is None  # placed none


def test_fight_participation(match):
    assert metrics.fight_participation(match, PHOENIX) == 1  # died in each of the five fights
    assert metrics.fight_participation(match, DAWNBREAKER) == 4 / 5  # no damage either way in the first
    assert metrics.fight_participation({**match, "teamfight_players": []}, PHOENIX) is None


def test_kill_participation(match):
    assert metrics.kill_participation(match, DAWNBREAKER) == (2 + 1) / 8
    assert metrics.kill_participation(match, SHADOW_FIEND) == (9 + 2) / 28
    assert metrics.kill_participation({**match, "players": []}, DAWNBREAKER) is None


def test_deaths_outside_fights(match):
    assert metrics.deaths_outside_fights(match, DAWNBREAKER) == 5  # six deaths, only the one at 14:03 in a fight
    assert metrics.deaths_outside_fights(match, PHOENIX) == 2  # 1:40 and 2:30
    assert metrics.deaths_outside_fights(match, SHADOW_FIEND) == 0  # never died


def test_every_metric_is_stored_and_served(session):
    count = dict(session.execute(select(Metric.name, func.count()).group_by(Metric.name)).all())
    assert set(count) == set(metrics.NAMES)
    assert count["kill_participation"] == 10
    assert count["obs_lifetime"] == 6  # the four players who placed no observer have no row

    assert queries.metric(session, queries.conditions(ME), "lane_cs_diff") == [
        {"match_id": MATCH_ID, "start_time": MATCH_ID, "value": -47}
    ]  # one value per parsed match; the unparsed match 7 has none
    averages = {r["name"]: r for r in queries.metric_averages(session, queries.conditions(ME))}
    assert averages["obs_lifetime"] == {"name": "obs_lifetime", "average": 347.5, "matches": 1}
    assert len(averages) == len(metrics.NAMES)

    derive_match(session, MATCH_ID, FIXTURES)  # again: rows are replaced, not added
    assert dict(session.execute(select(Metric.name, func.count()).group_by(Metric.name)).all()) == count
