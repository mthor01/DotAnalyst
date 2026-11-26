"""Explore: the live games, recent results and logos the poller keeps, and the answer built from them (made-up ids)."""
import json

import httpx

from dotanalyst import explore

NOW = 1_795_100_000
HOUR = 3600


def live_game(league_id=1003, match_id=9001, ugc=7001) -> dict:
    return {
        "league_id": league_id, "match_id": match_id, "series_type": 1, "radiant_series_wins": 1, "dire_series_wins": 0,
        "radiant_team": {"team_name": "Team A", "team_id": 3001, "team_logo": ugc},
        "dire_team": {"team_name": "Team B", "team_id": 3002, "team_logo": 0},
        "scoreboard": {"duration": 1234.5, "radiant": {"score": 20}, "dire": {"score": 11}},
    }  # fmt: skip


def test_parse_live_reads_series_clock_and_logo():
    (g,) = explore.parse_live([live_game()])
    assert (g["league_id"], g["match_id"], g["series"], g["best_of"], g["duration"], g["score"]) == (1003, 9001, [1, 0], 3, 1234.5, [20, 11])
    assert (g["radiant"]["name"], g["radiant"]["team_id"], g["radiant"]["logo_ugc"], g["dire"]["logo_ugc"]) == ("Team A", 3001, 7001, None)


def test_keep_live_writes_file(tmp_path):
    explore.keep_live([live_game()], tmp_path, NOW)
    kept = json.loads((tmp_path / "explore" / "live.json").read_text())
    assert kept["read"] == NOW and kept["games"][0]["match_id"] == 9001


def game(match_id, series_id, start, radiant, dire, radiant_win, series_type=1, league=1003, duration=2000) -> dict:
    return {
        "match_id": match_id, "series_id": series_id, "series_type": series_type, "start_time": start, "duration": duration,
        "leagueid": league, "league_name": "League A", "radiant_team_id": radiant[0], "radiant_name": radiant[1],
        "dire_team_id": dire[0], "dire_name": dire[1], "radiant_win": radiant_win,
    }  # fmt: skip


A, B, C, D = (3001, "Team A"), (3002, "Team B"), (3003, "Team C"), (3004, "Team D")


def test_series_grouped_and_finished_by_wins():
    games = [game(9002, 501, NOW - 2 * HOUR, B, A, False), game(9001, 501, NOW - 3 * HOUR, A, B, True),
             game(9003, 502, NOW - 600, C, D, True)]  # fmt: skip
    (s,) = explore.series_of(games, NOW)  # 502 has one game of a Bo3, just played: not finished
    assert [o["name"] for o in s["opponents"]] == ["Team A", "Team B"] and s["score"] == [2, 0] and s["winner"] == 0
    assert s["best_of"] == 3 and s["match_ids"] == [9001, 9002] and s["league_id"] == 1003 and s["league_name"] == "League A"
    assert [(m["team1side"], m["winner"]) for m in s["maps"]] == [("radiant", 0), ("dire", 0)]
    assert s["time"] == NOW - 2 * HOUR + 2000  # when its last game ended


def test_series_finished_after_three_hours():
    (s,) = explore.series_of([game(9001, 503, NOW - 4 * HOUR, A, B, False)], NOW)
    assert s["score"] == [0, 1] and s["winner"] == 1


def test_series_without_id_group_by_league_and_teams():
    games = [
        game(9001, 0, NOW - 5 * HOUR, A, B, True), game(9002, 0, NOW - 4 * HOUR, B, A, True),  # one Bo3, 1-1 so far
        game(9003, 0, NOW - 30 * HOUR, A, B, True),  # a day before: another series
        game(9004, 0, NOW - 4 * HOUR, (0, "Team G"), (0, "Team H"), True, series_type=0),  # Bo1s never merge
        game(9005, 0, NOW - 4 * HOUR, (0, "Team G"), (0, "Team H"), True, series_type=0),
        game(9006, 0, NOW - 4 * HOUR, A, B, True, league=1004),  # another league
    ]  # fmt: skip
    found = sorted(tuple(s["match_ids"]) for s in explore.series_of(games, NOW))
    assert found == [(9001, 9002), (9003,), (9004,), (9005,), (9006,)]


def test_fetch_results_skips_within_ten_minutes(tmp_path):
    asked: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return httpx.Response(200, json=[game(9001, 501, NOW - HOUR, A, B, True)])

    web = httpx.Client(transport=httpx.MockTransport(answer))
    assert explore.fetch_results(web, tmp_path, NOW) == 1 and asked[0].url.path == "/api/proMatches"
    assert explore.fetch_results(web, tmp_path, NOW + 500) == 0 and len(asked) == 1
    assert explore.fetch_results(web, tmp_path, NOW + explore.RESULTS_SECONDS) == 1 and len(asked) == 2
    failing = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert explore.fetch_results(failing, tmp_path, NOW + 10 * explore.RESULTS_SECONDS) == 0
    assert json.loads((tmp_path / "explore" / "results.json").read_text())["games"][0]["match_id"] == 9001  # kept


def test_remember_logos_merges(tmp_path):
    explore.remember_logos(tmp_path, [{"team_id": 3001, "name": "Team A", "logo": "a.png"}, {"team_id": 0, "name": "X", "logo": "x.png"}])
    explore.remember_logos(tmp_path, [{"team_id": 3002, "name": "Team B", "logo": "b.png"}, {"team_id": 3003, "name": "Team C", "logo": None}])
    assert explore.logos(tmp_path) == {"3001": {"name": "Team A", "logo": "a.png"}, "3002": {"name": "Team B", "logo": "b.png"}}
