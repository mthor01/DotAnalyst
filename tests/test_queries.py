import copy
import json
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst import queries
from dotanalyst.db import Account, Base, Derived, Lane, Metric, PlayerName
from dotanalyst.steam import ANONYMOUS, store_league_match, store_match

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
    Derived.metadata.create_all(engine)
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


def test_matches_carry_side_lane_and_company(session):
    session.add_all(
        [
            Lane(match_id=1, player_slot=0, lane="mid"),
            Metric(match_id=1, player_slot=0, name="lane_nw_diff", value=-250),
            Metric(match_id=1, player_slot=0, name="obs_placed", value=2),  # another metric must not double the row
        ]
    )
    rows = {r["match_id"]: r for r in queries.matches(session, queries.conditions(ME))}
    assert len(rows) == 3

    def extras(match_id):
        return tuple(rows[match_id][key] for key in ("radiant", "lane", "lane_nw_diff", "with_tracked"))

    assert extras(1) == (True, "mid", -250, True)
    assert extras(2) == (False, None, None, False)  # no replay stats; the friend was on the other team
    assert extras(3) == (True, None, None, True)


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


LEAGUE_TEMPLATE = json.loads(
    (Path(__file__).parent / "fixtures" / "league_details.json").read_text(encoding="utf-8")
)["result"]["matches"][0]
US, THEM, OTHER, NO_TEAM = 10, 20, 30, 0
TEAM_NAMES = {US: "Us", THEM: "Them", OTHER: "Other"}


def league_game(match_id, day, radiant, dire, radiant_win, radiant_bans, dire_bans, radiant_picks=(1, 2, 3, 4, 5), dire_picks=(6, 7, 8, 9, 10)):  # fmt: skip
    """The recorded league game with a known draft. Player i of team T is always account 100 * T + i."""
    m = copy.deepcopy(LEAGUE_TEMPLATE)
    m.update(
        match_id=match_id, start_time=int(datetime(2026, 11, day, 12).timestamp()), leagueid=20408,
        radiant_team_id=radiant, dire_team_id=dire, radiant_name=TEAM_NAMES.get(radiant),
        dire_name=TEAM_NAMES.get(dire), radiant_win=radiant_win,
    )
    drafted = [(False, 0, radiant_bans), (False, 1, dire_bans), (True, 0, radiant_picks), (True, 1, dire_picks)]
    m["picks_bans"] = [
        {"is_pick": is_pick, "hero_id": hero, "team": side, "order": 0} for is_pick, side, heroes in drafted for hero in heroes
    ]
    teams = [radiant] * 5 + [dire] * 5
    for i, (player, slot, hero) in enumerate(zip(m["players"], SLOTS, [*radiant_picks, *dire_picks])):
        player.update(player_slot=slot, hero_id=hero, account_id=100 * teams[i] + i % 5)
    return m


LEAGUE_GAMES = [
    # Them ban 50 and 51 against Us; Us win with heroes 1-5
    league_game(1, 1, US, THEM, True, radiant_bans=[60], dire_bans=[50, 51]),
    # Us on the Dire side: Them ban 50 again, Us ban 51 themselves, and lose with hero 11 in the last place
    league_game(2, 2, THEM, US, True, radiant_bans=[50], dire_bans=[51], dire_picks=(1, 2, 3, 4, 11)),
    # 50 and 51 are open: Us pick 50 and win, the other side takes 51
    league_game(3, 3, US, OTHER, True, radiant_bans=[], dire_bans=[52], radiant_picks=(50, 2, 3, 4, 5), dire_picks=(51, 7, 8, 9, 10)),
    league_game(4, 4, THEM, OTHER, True, radiant_bans=[50], dire_bans=[50]),  # not a game of Us
    league_game(5, 5, OTHER, NO_TEAM, False, radiant_bans=[], dire_bans=[]),  # the Dire side has no team
]  # fmt: skip


@pytest.fixture
def league():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        for m in LEAGUE_GAMES:
            store_league_match(s, m)
        s.add(PlayerName(account_id=1000, name="Carry"))
        s.commit()
        yield s


def test_teams_with_games_and_wins(league):
    assert queries.teams(league) == [
        {"team_id": OTHER, "name": "Other", "games": 3, "wins": 0, "last_played": LEAGUE_GAMES[4]["start_time"]},
        {"team_id": THEM, "name": "Them", "games": 3, "wins": 2, "last_played": LEAGUE_GAMES[3]["start_time"]},
        {"team_id": US, "name": "Us", "games": 3, "wins": 2, "last_played": LEAGUE_GAMES[2]["start_time"]},
    ]


def test_team_games_newest_first_from_the_teams_side(league):
    found = queries.team(league, US)
    assert (found["team_id"], found["name"]) == (US, "Us")
    assert [g["match_id"] for g in found["games"]] == [3, 2, 1]
    assert found["games"][1] == {
        "match_id": 2, "start_time": LEAGUE_GAMES[1]["start_time"], "league": "Season 8", "radiant": False,
        "win": False, "opponent_id": THEM, "opponent": "Them", "picks": [1, 2, 3, 4, 11], "bans": [51],
        "bans_against": [50],
    }  # fmt: skip
    assert [g["win"] for g in found["games"]] == [True, False, True]


def test_team_heroes_count_bans_against_and_picks_when_open(league):
    heroes = {h.pop("hero_id"): h for h in queries.team(league, US)["heroes"]}
    # 50: banned against Us in games 1 and 2, open in game 3, where Us picked it and won
    assert heroes[50] == {"banned_against": 2, "banned": 0, "open": 1, "picked": 1, "wins": 1}
    # 51: banned against Us once, banned by Us once, open once and then not picked
    assert heroes[51] == {"banned_against": 1, "banned": 1, "open": 1, "picked": 0, "wins": 0}
    assert heroes[52] == {"banned_against": 1, "banned": 0, "open": 2, "picked": 0, "wins": 0}
    assert heroes[60] == {"banned_against": 0, "banned": 1, "open": 2, "picked": 0, "wins": 0}
    assert heroes[1] == {"banned_against": 0, "banned": 0, "open": 3, "picked": 2, "wins": 1}
    assert heroes[2] == {"banned_against": 0, "banned": 0, "open": 3, "picked": 3, "wins": 2}
    assert heroes[11] == {"banned_against": 0, "banned": 0, "open": 3, "picked": 1, "wins": 0}
    assert 6 not in heroes  # only the other side ever touched it


def test_team_players_with_their_heroes(league):
    players = {p["account_id"]: p for p in queries.team(league, US)["players"]}
    assert set(players) == {1000, 1001, 1002, 1003, 1004}  # nobody of the other side
    assert players[1000] == {
        "account_id": 1000, "name": "Carry", "games": 3,
        "heroes": [{"hero_id": 1, "games": 2, "wins": 1}, {"hero_id": 50, "games": 1, "wins": 1}],
    }  # fmt: skip
    assert players[1004]["name"] is None  # Steam gave no name
    assert players[1004]["heroes"] == [{"hero_id": 5, "games": 2, "wins": 2}, {"hero_id": 11, "games": 1, "wins": 0}]


def test_team_without_games_is_none(league):
    assert queries.team(league, 99) is None
