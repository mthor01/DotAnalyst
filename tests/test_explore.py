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


# ---- which tournaments, and the answer of /api/explore
import time  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from dotanalyst import liquipedia  # noqa: E402
from dotanalyst.db import Base, Derived, LeagueCatalog  # noqa: E402

DAY = 86400


def date(at: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(at))


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    lp = dict(lp_checked=NOW - DAY)
    with Session(engine) as s:
        s.add_all([
            LeagueCatalog(league_id=1001, name="Big Live", lp_page="Big Live", lp_tier=1, prize_usd=10**6, live_seen=NOW, live_games=1,
                          first_game=NOW - 3 * DAY, last_game=NOW - HOUR, region="Europe", location="Online, Europe", **lp),
            LeagueCatalog(league_id=1002, name="Active Two", lp_page="Active Two", lp_tier=2, first_game=NOW - 9 * DAY,
                          last_game=NOW - 2 * DAY, location="Moscow, Russia", **lp),  # region never asked: None
            LeagueCatalog(league_id=1003, name="Soon", lp_page="Soon", lp_tier=3, start_date=date(NOW + 5 * DAY),
                          end_date=date(NOW + 10 * DAY), region="", **lp),
            LeagueCatalog(league_id=1004, name="Done", lp_page="Done", lp_tier=1, first_game=NOW - 20 * DAY, last_game=NOW - 10 * DAY,
                          start_date=date(NOW - 20 * DAY), end_date=date(NOW - 10 * DAY), region="SEA", **lp),
            LeagueCatalog(league_id=1005, name="Old", lp_page="Old", lp_tier=1, last_game=NOW - 100 * DAY, end_date=date(NOW - 100 * DAY), **lp),
            LeagueCatalog(league_id=1006, name="Tier Four", lp_page="Tier Four", lp_tier=4, live_seen=NOW, live_games=1, **lp),
            LeagueCatalog(league_id=1007, name="No Page", live_seen=NOW, live_games=1),
            LeagueCatalog(league_id=2001, name="New Pro", tier="professional"),
            LeagueCatalog(league_id=2002, name="New Premium", tier="premium"),
            LeagueCatalog(league_id=2003, name="Played", tier="premium", games=5),
            LeagueCatalog(league_id=2004, name="Amateur", tier="amateur"),
            LeagueCatalog(league_id=2005, name="Asked", tier="professional", lp_checked=NOW),
        ])  # fmt: skip
        s.commit()
        yield s


def test_tournaments_pick_and_order(session):
    assert [r.league_id for r in explore.tournaments(session, NOW)] == [1001, 1004, 1002, 1003]  # live, then tier


def test_newcomers_and_missing_region(session):
    assert explore.newcomers(session) == [2002, 2001] and explore.newcomers(session, n=1) == [2002]
    assert 1002 in explore.missing_region(session)


def test_missing_region_skips_empty(session):
    assert 1003 not in explore.missing_region(session)  # asked, none said
    assert 1007 not in explore.missing_region(session)  # no Liquipedia page


def keep(data, league_id: int, found: dict, page: str) -> None:
    path = data / "leagues" / f"{league_id}.lp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": liquipedia.VERSION, "fetched": NOW, "page": page, "found": found}))


def upcoming(at: float, a="Team A", b="Team B") -> dict:
    return {"opponents": [a, b], "time": at, "match_ids": [], "maps": [], "score": [0, 0], "winner": None, "best_of": 3}


def fill(data) -> None:
    games = [live_game(1007, 9007), live_game(1001, 9001), live_game(1006, 9006)]
    games[0]["scoreboard"]["duration"], games[1]["scoreboard"]["duration"] = 900, 500
    explore.keep_live(games, data, NOW - 60)
    explore.remember_logos(data, [{"team_id": 3001, "name": "Team A", "logo": "a.png"}])
    (data / "explore" / "results.json").write_text(json.dumps({"read": NOW, "games": [
        game(9101, 601, NOW - 3 * HOUR, A, B, True, league=1002), game(9102, 601, NOW - 2 * HOUR, B, A, False, league=1002)]}))
    keep(data, 1001, {"upcoming": [upcoming(NOW + 2 * HOUR), upcoming(NOW + 30 * HOUR)], "winner": None}, "Big Live")
    keep(data, 1004, {"upcoming": [], "winner": "team a"}, "Done")


def test_answer_sections(session, tmp_path):
    fill(tmp_path)
    a = explore.answer(session, tmp_path, NOW)
    assert [g["match_id"] for g in a["live"]] == [9001, 9006, 9007]  # tier 1, tier 4, no tier
    assert a["live"][0]["radiant"]["logo"] == "a.png" and a["live"][0]["dire"]["logo"] is None
    (u,) = a["upcoming"]
    assert u["league_id"] == 1001 and u["opponents"][0] == {"name": "Team A", "team_id": 3001, "logo": "a.png"}
    assert u["opponents"][1] == {"name": "Team B", "team_id": 0, "logo": None}
    assert [(r["league_id"], r["score"]) for r in a["results"]] == [(1002, [2, 0])]
    assert a["soon"] == [1003]
    assert a["finished"] == [{"league_id": 1004, "winner": {"name": "team a", "logo": "a.png"}}]
    assert {c["league_id"] for c in a["calendar"]} == {1001, 1002, 1003, 1004}
    assert a["big"][:2] == [1001, 1004]
    leagues = a["leagues"]
    assert {1001, 1002, 1003, 1004, 1006, 1007} <= {int(k) for k in leagues}
    assert (leagues["1001"]["region"], leagues["1001"]["online"], leagues["1002"]["online"]) == ("Europe", True, False)


def test_live_older_than_fifteen_minutes_is_not_shown(session, tmp_path):
    explore.keep_live([live_game(1001, 9001)], tmp_path, NOW - 16 * 60)
    assert explore.answer(session, tmp_path, NOW)["live"] == []


def test_upcoming_window_24h(session, tmp_path):
    keep(tmp_path, 1001, {"upcoming": [upcoming(NOW - 60), upcoming(NOW + DAY), upcoming(NOW + DAY + 1),
                                       upcoming(NOW + HOUR, b=None)], "winner": None}, "Big Live")  # fmt: skip
    assert [u["time"] for u in explore.answer(session, tmp_path, NOW)["upcoming"]] == [NOW + DAY]


def test_answer_without_files(session, tmp_path):
    (tmp_path / "explore").mkdir()
    (tmp_path / "explore" / "live.json").write_text("{broken")
    a = explore.answer(session, tmp_path, NOW)
    assert a["live"] == [] and a["upcoming"] == [] and a["results"] == []
    assert a["finished"] == [{"league_id": 1004, "winner": None}]


def test_finished_winner_unknown_for_old_structure(session, tmp_path):
    keep(tmp_path, 1004, {"upcoming": []}, "Done")  # kept before winners were read
    assert explore.answer(session, tmp_path, NOW)["finished"] == [{"league_id": 1004, "winner": None}]


def test_calendar_uses_game_dates_and_open_end(session, tmp_path):
    cal = {c["league_id"]: c for c in explore.answer(session, tmp_path, NOW)["calendar"]}
    assert (cal[1001]["start"], cal[1001]["end"], cal[1001]["open"]) == (NOW - 3 * DAY, NOW, True)  # still playing
    assert cal[1003]["start"] == liquipedia.catalog.day_end(date(NOW + 5 * DAY)) - 86399 and not cal[1003]["open"]
    assert cal[1004]["end"] == liquipedia.catalog.day_end(date(NOW - 10 * DAY))
    assert 1005 not in cal  # out of the window


# ---- the poller fills it
from dotanalyst import poll  # noqa: E402


def test_live_step_keeps_games(monkeypatch, tmp_path, session):
    monkeypatch.setattr(poll, "call", lambda client, key, path, **kw: {"games": [live_game(1001, 9001, ugc=7001)]})
    asked = []
    monkeypatch.setattr(explore.steam, "team_logo", lambda client, key, ugc, data: asked.append(ugc) or f"{ugc}.png")
    assert poll.live_step(session, httpx.Client(), poll.Setup("key", None, tmp_path)) == 1
    assert json.loads((tmp_path / "explore" / "live.json").read_text())["games"][0]["match_id"] == 9001
    assert asked == [7001] and explore.logos(tmp_path) == {"3001": {"name": "Team A", "logo": "7001.png"}}


def test_live_logos_capped(monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(explore.steam, "team_logo", lambda client, key, ugc, data: asked.append(ugc) or "x.png")
    games = explore.parse_live([live_game(1001, 9000 + i, ugc=7000 + i) for i in range(12)])
    for i, g in enumerate(games):
        g["radiant"]["team_id"] = 3100 + i
    explore.live_logos(httpx.Client(), "key", games, tmp_path)
    assert len(asked) == explore.LOGOS_PER_ROUND


def test_catalog_step_fills_explore(monkeypatch, tmp_path, session):
    calls: dict[str, list] = {"results": [], "lookups": [], "structures": []}
    monkeypatch.setattr(poll.catalog, "refresh", lambda s, c, now: 0)
    monkeypatch.setattr(poll.explore, "fetch_results", lambda c, data, now: calls["results"].append(data) or 0)
    monkeypatch.setattr(poll.liquipedia, "lookup", lambda s, c, league_id, now: calls["lookups"].append(league_id) or False)
    monkeypatch.setattr(poll.liquipedia, "structure", lambda c, row, data, now, finished: calls["structures"].append(row.league_id))
    monkeypatch.setattr(poll, "STRUCTURES", 2)
    poll.catalog_step(session, httpx.Client(), poll.Setup("key", None, tmp_path), NOW)
    assert calls["results"] == [tmp_path]
    assert {2001, 2002, 1002} <= set(calls["lookups"])  # newcomers, and a region never asked
    assert 1003 not in calls["lookups"]  # asked a day ago, region said none
    assert calls["structures"] == [1001, 1004]  # the first two due, live first


def test_finished_winner_decided_by_our_games(session, tmp_path):
    from dotanalyst.db import LeagueMatch

    final = {"opponents": ["Team A", "Team B"], "time": NOW - 10 * DAY, "match_ids": [9301, 9302], "score": [0, 0],
             "winner": None, "best_of": 3, "maps": [{"team1side": "radiant", "winner": None, "match_id": 9301},
                                                    {"team1side": "dire", "winner": None, "match_id": 9302}]}  # fmt: skip
    keep(tmp_path, 1004, {"upcoming": [], "winner": None, "final": final}, "Done")
    session.add(LeagueMatch(match_id=9301, league_id=1004, start_time=NOW - 10 * DAY, radiant_team_id=3001, dire_team_id=3002,
                            radiant_win=False, raw_json={}))
    session.commit()
    preview = tmp_path / "leagues" / "1004.json"
    preview.write_text(json.dumps({"games": [{"match_id": 9302, "radiant_win": True}]}))
    assert explore.answer(session, tmp_path, NOW)["finished"] == [{"league_id": 1004, "winner": {"name": "Team B", "logo": None}}]


# ---- Home: Explore of your tournaments
from dotanalyst.db import League, LeagueMatch  # noqa: E402


def stored(match_id, league, start, radiant, dire, radiant_win, series=None) -> LeagueMatch:
    raw = {"duration": 2000, **({"series_id": series[0], "series_type": series[1]} if series else {})}
    return LeagueMatch(match_id=match_id, league_id=league, start_time=start, radiant_team_id=radiant[0], dire_team_id=dire[0],
                       radiant_name=radiant[1], dire_name=dire[1], radiant_win=radiant_win, raw_json=raw)  # fmt: skip


def test_home_shows_only_your_tournaments(session, tmp_path):
    fill(tmp_path)
    keep(tmp_path, 1001, {"upcoming": [upcoming(NOW + 6 * DAY), upcoming(NOW + 2 * HOUR), upcoming(NOW + 8 * DAY)]}, "Big Live")
    session.add_all([
        League(league_id=1001, name="Big Live"), League(league_id=1007, name="No Page"),
        stored(9401, 1001, NOW - 5 * HOUR, A, B, True, (701, 1)), stored(9402, 1001, NOW - 4 * HOUR, B, A, False, (701, 1)),
        stored(9403, 1007, NOW - 8 * DAY, A, B, True),  # over 7 days ago
        stored(9404, 1002, NOW - 5 * HOUR, A, B, True),  # not yours
    ])  # fmt: skip
    session.commit()
    h = explore.home(session, tmp_path, NOW)
    assert [g["match_id"] for g in h["live"]] == [9001, 9007]
    assert [u["time"] for u in h["upcoming"]] == [NOW + 2 * HOUR, NOW + 6 * DAY]  # 7 days
    (r,) = h["results"]
    assert (r["match_ids"], r["score"], r["winner"], r["best_of"]) == ([9401, 9402], [2, 0], 0, 3)
    assert (r["league_id"], r["league_name"], r["opponents"][0]["logo"]) == (1001, "Big Live", "a.png")
    assert h["mine"] == [1001, 1007] and set(h["leagues"]) == {"1001", "1007"}


def test_home_results_without_series_ids(session, tmp_path):
    # stored before the series id was kept: the same teams within 6 hours are one series, of a length not known
    session.add_all([
        League(league_id=1002, name="Active Two"),
        stored(9501, 1002, NOW - 6 * HOUR, A, B, True), stored(9502, 1002, NOW - 5 * HOUR, B, A, True),
        stored(9503, 1002, NOW - HOUR, C, D, True),  # may go on: not a result yet
    ])  # fmt: skip
    session.commit()
    (r,) = explore.home(session, tmp_path, NOW)["results"]
    assert (r["match_ids"], r["score"], r["winner"], r["best_of"]) == ([9501, 9502], [1, 1], None, None)


def test_home_without_tournaments(session, tmp_path):
    assert explore.home(session, tmp_path, NOW) == {"leagues": {}, "live": [], "upcoming": [], "results": [], "mine": []}


def test_catalog_step_reads_your_tournaments_brackets_first(monkeypatch, tmp_path, session):
    read: list[tuple[int, bool]] = []
    monkeypatch.setattr(poll.catalog, "refresh", lambda s, c, now: 0)
    monkeypatch.setattr(poll.explore, "fetch_results", lambda c, data, now: 0)
    monkeypatch.setattr(poll.liquipedia, "lookup", lambda s, c, league_id, now: False)
    monkeypatch.setattr(poll.liquipedia, "structure", lambda c, row, data, now, finished: read.append((row.league_id, finished)))
    session.add_all([League(league_id=1006, name="Tier Four"), League(league_id=1005, name="Old")])  # tier 4; over 100 days ago
    session.commit()
    poll.catalog_step(session, httpx.Client(), poll.Setup("key", None, tmp_path), NOW)
    assert read[:2] == [(1005, True), (1006, False)]  # yours, though Explore follows neither; a finished one read once
    assert [i for i, _ in read[2:]] == [1001, 1004, 1002, 1003]
