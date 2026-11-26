"""The tournament page: stored games for a subscribed league, else a preview from OpenDota (pro) or Steam (amateur)."""
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from dotanalyst import league_page, steam
from dotanalyst.db import Base, Derived, League, LeagueCatalog, LeagueMatch

FIXTURES = Path(__file__).parent / "fixtures"
NOW = 1_795_100_000
DAY = 86400
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


def history() -> list[dict]:
    return json.loads((FIXTURES / "league_history.json").read_text())["result"]["matches"]


def client(asked: list[httpx.Request], opendota_games: bool = True) -> httpx.Client:
    """OpenDota's league games and teams (none for an amateur league), Steam's league history and match details."""
    by_seq = {e["match_seq_num"]: e for e in history()}

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        path = request.url.path
        if path.endswith("/matches"):
            return httpx.Response(200, content=(FIXTURES / "od_league_matches.json").read_bytes() if opendota_games else b"[]")
        if path.endswith("/teams"):
            return httpx.Response(200, content=(FIXTURES / "od_league_teams.json").read_bytes() if opendota_games else b"[]")
        if "GetMatchHistory/" in path:
            listed = [] if "start_at_match_id" in request.url.params else history()
            return httpx.Response(200, json={"result": {"status": 1, "matches": listed}})
        if "GetMatchHistoryBySequenceNum" in path:
            e = by_seq[int(request.url.params["start_at_match_seq_num"])]
            found = {**e, "leagueid": 1003, "radiant_win": True, "radiant_score": 20, "dire_score": 5,
                     "radiant_name": "Team A", "dire_name": "Team B"}  # fmt: skip
            return httpx.Response(200, json={"result": {"status": 1, "matches": [found]}})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(answer))


def test_a_subscribed_league_shows_its_stored_games(session, tmp_path):
    session.add(League(league_id=1003, name="Friday Amateur League S9"))
    for e in history():
        session.add(LeagueMatch(match_id=e["match_id"], league_id=1003, start_time=e["start_time"],
                                radiant_team_id=e["radiant_team_id"], dire_team_id=e["dire_team_id"], radiant_name="Team A",
                                dire_name="Team B", radiant_win=True, raw_json={"radiant_score": 20, "dire_score": 5}))  # fmt: skip
    session.commit()
    asked: list[httpx.Request] = []
    page = league_page.page(session, client(asked), "key", 1003, tmp_path, NOW)
    assert page["source"] == "stored" and page["subscribed"]
    assert len(page["games"]) == 3 and page["games"][0]["start_time"] >= page["games"][-1]["start_time"]
    assert page["games"][0]["radiant"]["name"] == "Team A" and page["games"][0]["radiant_score"] == 20
    assert {g["series_id"] for g in page["games"]} == {e["series_id"] for e in history()}  # from Steam's list
    assert not any("BySequenceNum" in r.url.path or "opendota" in r.url.host for r in asked)  # nothing refetched


def test_a_pro_league_previews_from_opendota_and_caches_it(session, tmp_path):
    asked: list[httpx.Request] = []
    page = league_page.page(session, client(asked), "key", 1002, tmp_path, NOW)
    assert page["source"] == "opendota" and len(page["games"]) == 6 and len(asked) == 2
    assert (tmp_path / "leagues" / "1002.json").exists()
    a = next(t for t in page["teams"] if t["team_id"] == 3001)
    assert (a["name"], a["rating"], a["logo"], a["games"], a["wins"]) == ("Team A", 1200.5, "https://example.invalid/3001.png", 4, 2)
    row = session.get(LeagueCatalog, 1002)
    assert (row.games, row.last_game) == (6, 1795000000 - 3000)
    league_page.page(session, client(asked), "key", 1002, tmp_path, NOW + 5 * HOUR)
    assert len(asked) == 2  # within PREVIEW_HOURS: from the file
    league_page.page(session, client(asked), "key", 1002, tmp_path, NOW + 7 * HOUR)
    assert len(asked) == 4  # still playing and older: fetched again


def test_an_amateur_league_falls_back_to_steam(session, tmp_path, monkeypatch):
    monkeypatch.setattr(league_page, "STEAM_DETAILS", 2)
    asked: list[httpx.Request] = []
    page = league_page.page(session, client(asked, opendota_games=False), "key", 1003, tmp_path, NOW)
    assert page["source"] == "steam" and len(page["games"]) == 3
    assert sum("BySequenceNum" in r.url.path for r in asked) == 2  # the newest two only
    detailed = [g for g in page["games"] if g["radiant_win"] is not None]
    assert len(detailed) == 2 and detailed[0]["radiant"]["name"] == "Team A"
    assert page["games"][-1]["radiant_win"] is None and page["games"][-1]["radiant"]["team_id"]  # ids, no result


def test_without_a_key_an_amateur_league_has_no_games(session, tmp_path):
    page = league_page.page(session, client([], opendota_games=False), "", 1003, tmp_path, NOW)
    assert page["source"] == "none" and page["games"] == []


def test_a_finished_league_preview_is_never_fetched_again(session, tmp_path):
    league_page.page(session, client([]), "key", 1002, tmp_path, NOW)
    asked: list[httpx.Request] = []
    page = league_page.page(session, client(asked), "key", 1002, tmp_path, NOW + 60 * DAY)
    assert asked == [] and len(page["games"]) == 6


def test_series_scores_and_bo_types():
    games = [league_page.from_opendota(g) for g in json.loads((FIXTURES / "od_league_matches.json").read_text())]
    found = {s["series_id"]: s for s in league_page.series(games)}
    bo3 = found[501]
    assert bo3["best_of"] == 3 and [t["team_id"] for t in bo3["teams"]] == [3001, 3002] and bo3["score"] == [2, 1]
    assert found[502]["best_of"] == 1 and found[502]["score"] == [1, 0]
    assert found[503]["score"] == [2, 0] and found[503]["teams"][0]["team_id"] == 3002
    assert [s["series_id"] for s in league_page.series(games)] == [501, 502, 503]  # newest first


def test_preview_games_stay_out_of_league_matches(session, tmp_path):
    league_page.page(session, client([]), "key", 1002, tmp_path, NOW)
    assert session.scalar(select(func.count()).select_from(LeagueMatch)) == 0


def test_a_league_liquipedia_was_never_asked_about_is_looked_up(session, tmp_path, monkeypatch):
    looked = []
    monkeypatch.setattr(league_page.liquipedia, "lookup", lambda s, c, league_id, now: looked.append(league_id))
    session.get(LeagueCatalog, 1002).lp_checked = None
    league_page.page(session, client([]), "key", 1002, tmp_path, NOW)
    assert looked == [1002]
