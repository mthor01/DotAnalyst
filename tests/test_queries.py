import copy
import json
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst import queries
from dotanalyst.db import Account, Base, Derived, Lane, Match, Metric, PlayerGame, PlayerGameList, PlayerName, Ward
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
    assert rows[1]["position"] == 2  # the only one in mid
    assert {r["position"] for r in rows.values()} <= {1, 2, 3, 4, 5}
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
    store_league_match(session, {**MATCHES[1], "leagueid": 19418})  # match 2 was a league game
    assert found(league_id=19418) == [2]
    assert found(league_id=20408) == []


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


def test_wards_of_the_account_with_the_side_it_played(session):
    ward = {"removed": None, "killed": False, "killed_by": None}
    session.add_all(
        [
            Ward(match_id=1, player_slot=0, type="obs", x=100.0, y=90.0, placed=-30, **ward),  # mine, as Radiant
            Ward(match_id=2, player_slot=128, type="sen", x=150.0, y=140.0, placed=720, **ward),  # mine, as Dire
            Ward(match_id=2, player_slot=0, type="obs", x=1.0, y=1.0, placed=0, **ward),  # the friend's
        ]
    )
    assert queries.wards(session, queries.conditions(ME)) == [
        {"match_id": 1, "type": "obs", "x": 100.0, "y": 90.0, "radiant": True, "time": -30},
        {"match_id": 2, "type": "sen", "x": 150.0, "y": 140.0, "radiant": False, "time": 720},
    ]
    assert queries.wards(session, queries.conditions(ME, date_to=date(2026, 6, 10))) == [
        {"match_id": 1, "type": "obs", "x": 100.0, "y": 90.0, "radiant": True, "time": -30},
    ]


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
    league_game(2, 2, THEM, US, True, radiant_bans=[50], dire_bans=[51], radiant_picks=(6, 7, 8, 9, 10), dire_picks=(1, 2, 3, 4, 11)),
    # 50 and 51 are open: Us pick 50 and win, the other side takes 51
    league_game(3, 3, US, OTHER, True, radiant_bans=[], dire_bans=[52], radiant_picks=(50, 2, 3, 4, 5), dire_picks=(51, 7, 8, 9, 10)),
    league_game(4, 4, THEM, OTHER, True, radiant_bans=[50], dire_bans=[50]),  # not a game of Us
    league_game(5, 5, OTHER, NO_TEAM, False, radiant_bans=[], dire_bans=[]),  # the Dire side has no team
]  # fmt: skip
LEAGUE_GAMES[3]["dire_name"] = LEAGUE_GAMES[4]["radiant_name"] = ""  # Steam sends some games with an empty team name
LEAGUE_GAMES[0]["leagueid"] = 19418  # the first game is of the season before


@pytest.fixture
def league():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
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
        "win": False, "opponent_id": THEM, "opponent": "Them", "picks": [1, 2, 3, 4, 11],
        "picks_against": [6, 7, 8, 9, 10], "bans": [51],
        "bans_against": [50], "replay": False,
    }  # fmt: skip
    assert [g["win"] for g in found["games"]] == [True, False, True]


def test_team_heroes_count_bans_against_and_picks_when_open(league):
    heroes = {h.pop("hero_id"): h for h in queries.team(league, US)["heroes"]}
    # 50: banned against Us in games 1 and 2, open in game 3, where Us picked it and won
    assert heroes[50] == {"banned_against": 2, "banned": 0, "picked_against": 0, "open": 1, "picked": 1, "wins": 1}
    # 51: banned against Us once, banned by Us once, and in game 3 the other side took it: never open
    assert heroes[51] == {"banned_against": 1, "banned": 1, "picked_against": 1, "open": 0, "picked": 0, "wins": 0}
    assert heroes[52] == {"banned_against": 1, "banned": 0, "picked_against": 0, "open": 2, "picked": 0, "wins": 0}
    assert heroes[60] == {"banned_against": 0, "banned": 1, "picked_against": 0, "open": 2, "picked": 0, "wins": 0}
    assert heroes[1] == {"banned_against": 0, "banned": 0, "picked_against": 0, "open": 3, "picked": 2, "wins": 1}
    assert heroes[2] == {"banned_against": 0, "banned": 0, "picked_against": 0, "open": 3, "picked": 3, "wins": 2}
    assert heroes[11] == {"banned_against": 0, "banned": 0, "picked_against": 0, "open": 3, "picked": 1, "wins": 0}
    # 6: Them picked it in both games against Us, so Us could have taken it only in game 3
    assert heroes[6] == {"banned_against": 0, "banned": 0, "picked_against": 2, "open": 1, "picked": 0, "wins": 0}


def test_team_players_with_their_heroes(league):
    players = {p["account_id"]: p for p in queries.team(league, US)["players"]}
    assert set(players) == {1000, 1001, 1002, 1003, 1004}  # nobody of the other side
    assert (players[1000]["name"], players[1000]["games"]) == ("Carry", 3)
    assert players[1004]["name"] is None  # Steam gave no name
    played = [(h["hero_id"], h["games"], h["wins"]) for h in players[1004]["heroes"]]
    assert played == [(5, 2, 2), (11, 1, 0)]
    # the averages on a hero. Player 1000 is the recorded game's first player as Radiant (games 1 and 3) and its
    # sixth as Dire (game 2), so on hero 1 the two scoreboards are averaged, and hero 50 has the first one's numbers
    first, sixth = LEAGUE_TEMPLATE["players"][0], LEAGUE_TEMPLATE["players"][5]
    on_1, on_50 = players[1000]["heroes"]
    assert (on_1["hero_id"], on_50["hero_id"]) == (1, 50)
    for stat in ("kills", "deaths", "assists", "last_hits", "gold_per_min", "xp_per_min"):
        assert on_1[stat] == (first[stat] + sixth[stat]) / 2
        assert on_50[stat] == first[stat]


def test_team_players_wards_come_from_the_games_with_a_parsed_replay(league):
    assert all(not g["replay"] for g in queries.team(league, US)["games"])
    assert queries.team(league, US)["players"][0]["replays"] == 0
    store_match(league, LEAGUE_GAMES[1])  # what asking for its replay does; Us play Dire in it
    league.get(Match, 2).replay_state = "parsed"
    ward = {"placed": 0, "removed": None, "killed": False, "killed_by": None}
    league.add_all(
        [
            Ward(match_id=2, player_slot=128, type="obs", x=150.0, y=140.0, **ward),  # by 1000 of Us
            Ward(match_id=2, player_slot=0, type="sen", x=100.0, y=90.0, **ward),  # by one of Them
        ]
    )
    found = queries.team(league, US)
    assert [g["replay"] for g in found["games"]] == [False, True, False]
    players = {p["account_id"]: p for p in found["players"]}
    assert players[1000]["replays"] == 1
    assert players[1000]["wards"] == [
        {"match_id": 2, "type": "obs", "x": 150.0, "y": 140.0, "radiant": False, "time": 0, "league": True}
    ]
    assert players[1000]["parsed"] == [{"radiant": False, "league": True}]  # its games, wards or none
    assert players[1001]["wards"] == []


def test_team_players_wards_also_come_from_their_parsed_games_outside_the_league(league):
    ward = {"removed": None, "killed": False, "killed_by": None}
    store_match(league, make_match(90, (11, 3), True, {129: 1000}))  # a ranked game of player 1000, as Dire
    store_match(league, make_match(91, (11, 3), True, {0: 1001}))  # no parsed replay
    league.get(Match, 90).replay_state = "parsed"
    league.add_all(
        [
            Ward(match_id=90, player_slot=129, type="sen", x=60.0, y=70.0, placed=700, **ward),
            Ward(match_id=90, player_slot=0, type="obs", x=1.0, y=1.0, placed=0, **ward),  # someone else's
            Ward(match_id=91, player_slot=0, type="obs", x=1.0, y=1.0, placed=0, **ward),
        ]
    )
    players = {p["account_id"]: p for p in queries.team(league, US)["players"]}
    assert (players[1000]["usual_replays"], players[1001]["usual_replays"]) == (1, 0)
    assert players[1000]["wards"] == [
        {"match_id": 90, "type": "sen", "x": 60.0, "y": 70.0, "radiant": False, "time": 700, "league": False}
    ]
    assert players[1000]["parsed"] == [{"radiant": False, "league": False}]
    assert players[1001]["wards"] == []
    # the dates narrow them like the league games; the season does not, as they are in none
    assert queries.team(league, US, date_to=date(2026, 11, 2))["players"][0]["wards"] == []
    assert queries.team(league, US, league_id=20408)["players"][0]["usual_replays"] == 1


def test_team_players_games_outside_the_league_whatever_the_filters(league):
    game = {"start_time": 1, "game_mode": 22, "lobby_type": 7, "kills": 4, "deaths": 2, "assists": 9}
    league.add_all(
        [
            PlayerGameList(account_id=1000, fetched_at=0),
            PlayerGame(account_id=1000, match_id=91, hero_id=8, player_slot=129, radiant_win=False, lane_role=3, **game),
            PlayerGame(account_id=1000, match_id=92, hero_id=8, player_slot=0, radiant_win=False, lane_role=None,
                       **{**game, "start_time": 2}),
        ]
    )  # fmt: skip
    players = {p["account_id"]: p for p in queries.team(league, US, league_id=19418)["players"]}
    assert players[1000]["outside_listed"]
    assert players[1000]["outside"] == [  # newest first; a Dire player wins when Radiant loses
        {"match_id": 92, "hero_id": 8, "win": False, "role": "none", "kills": 4, "deaths": 2, "assists": 9},
        {"match_id": 91, "hero_id": 8, "win": True, "role": "off", "kills": 4, "deaths": 2, "assists": 9},
    ]
    assert (players[1001]["outside_listed"], players[1001]["outside"]) == (False, [])


def test_a_league_game_is_a_match_page_before_its_replay_was_asked_for(league):
    found = queries.match(league, 2)
    assert (found["match_id"], found["radiant_win"], found["replay_state"]) == (2, True, "none")
    assert found["start_time"] == LEAGUE_GAMES[1]["start_time"]
    assert [p["player_slot"] for p in found["players"]] == SLOTS
    assert [p["hero_id"] for p in found["players"]] == [6, 7, 8, 9, 10, 1, 2, 3, 4, 11]
    first = LEAGUE_TEMPLATE["players"][0]
    assert (found["players"][0]["kills"], found["players"][0]["net_worth"]) == (first["kills"], first["net_worth"])
    assert found["players"][5]["account_id"] == 1000 and found["players"][5]["label"] is None
    assert found["wards"] == [] and found["player_minute"] == []
    assert queries.match(league, 99) is None


def test_team_name_is_the_newest_one_that_is_not_empty(league):
    assert queries.team(league, OTHER)["name"] == "Other"
    assert queries.team(league, THEM)["games"][0]["opponent"] == "Other"  # game 4 itself has no name for them


def test_team_without_games_is_none(league):
    assert queries.team(league, 99) is None


def test_team_games_narrowed_by_dates_and_season(league):
    def games(**filters):
        return [g["match_id"] for g in queries.team(league, US, **filters)["games"]]

    assert games(date_from=date(2026, 11, 2)) == [3, 2]
    assert games(date_to=date(2026, 11, 2)) == [2, 1]  # the end day is included
    assert games(league_id=20408) == [3, 2]
    assert games(league_id=19418) == [1]
    empty = queries.team(league, US, date_from=date(2026, 12, 1))  # a known team without a game in the time frame
    assert (empty["name"], empty["games"], empty["heroes"], empty["players"]) == ("Us", [], [], [])
    heroes = {h["hero_id"]: h for h in queries.team(league, US, league_id=20408)["heroes"]}
    assert heroes[50]["banned_against"] == 1  # game 1, where Them banned it too, is not counted


def player(slot, lane, last_hits, net_worth=0):
    return {"player_slot": slot, "lane": lane, "last_hits": last_hits, "net_worth": net_worth}


def test_positions_from_lanes_and_farm():
    team = [player(0, "safe", 40), player(1, "safe", 200), player(2, "mid", 150), player(3, "off", 90), player(4, "off", 20)]
    assert queries.positions(team) == {1: 1, 0: 5, 2: 2, 3: 3, 4: 4}


def test_positions_leave_the_rest_to_farm():
    # a solo safe lane and a jungler: the safe lane gives only 1, so the jungler takes the 5 left
    team = [player(0, "safe", 220), player(1, "mid", 160), player(2, "off", 80), player(3, "off", 10), player(4, "jungle", 5, 900)]
    assert queries.positions(team) == {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}
    # a trilane: its least farmed has no place in the lane and takes what is left
    team = [player(0, "safe", 220), player(1, "mid", 160), player(2, "off", 80), player(3, "off", 10, 500), player(4, "off", 10, 400)]
    assert queries.positions(team)[3] == 4 and queries.positions(team)[4] == 5  # net worth breaks a tie in last hits


def test_positions_without_a_replay_rank_the_farm():
    team = [player(s, None, lh) for s, lh in zip(range(5), (30, 250, 10, 120, 180))]
    assert queries.positions(team) == {1: 1, 4: 2, 3: 3, 0: 4, 2: 5}
