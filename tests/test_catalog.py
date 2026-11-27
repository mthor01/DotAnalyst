"""The tournament browser's catalog: every league from OpenDota, the live ones from Steam, search and explore."""
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from dotanalyst import catalog
from dotanalyst.db import Base, Derived, LeagueCatalog

FIXTURES = Path(__file__).parent / "fixtures"
NOW = 1_795_100_000  # a day after the last game of league 1002
DAY = 86400


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def opendota(asked: list[str], leagues: list | None = None):
    """A client answering OpenDota's league list and explorer from the fixtures, remembering what was asked."""
    listed = leagues if leagues is not None else json.loads((FIXTURES / "od_leagues.json").read_text())

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        if request.url.path == "/api/explorer":
            return httpx.Response(200, content=(FIXTURES / "od_explorer.json").read_bytes())
        return httpx.Response(200, json=listed)

    return httpx.Client(transport=httpx.MockTransport(answer))


def test_refresh_adds_every_league_and_the_pro_dates(session):
    assert catalog.refresh(session, opendota([]), NOW) == 4
    pro = session.get(LeagueCatalog, 1002)
    assert (pro.name, pro.tier, pro.games, pro.first_game, pro.last_game) == ("Pro Series 5", "professional", 40, 1790000000, 1795000000)
    amateur = session.get(LeagueCatalog, 1003)
    assert amateur.tier == "excluded" and amateur.games is None and amateur.last_game is None


def test_refresh_keeps_rows_and_their_liquipedia_fields(session):
    catalog.refresh(session, opendota([]), NOW)
    session.get(LeagueCatalog, 1001).lp_tier = 1
    session.commit()
    renamed = [{"leagueid": 1001, "tier": "premium", "name": "Grand Cup 2026 Finals"}]  # the others left the list
    catalog.refresh(session, opendota([], renamed), NOW + 2 * DAY)
    cup = session.get(LeagueCatalog, 1001)
    assert cup.name == "Grand Cup 2026 Finals" and cup.lp_tier == 1
    assert len(session.scalars(select(LeagueCatalog)).all()) == 4


def test_refresh_waits_a_day(session):
    asked: list[str] = []
    catalog.refresh(session, opendota(asked), NOW)
    assert asked == ["/api/leagues", "/api/explorer"]
    assert catalog.refresh(session, opendota(asked), NOW + DAY - 60) == 0
    assert len(asked) == 2


def live() -> list[dict]:
    return json.loads((FIXTURES / "steam_live.json").read_text())["result"]["games"]


def test_live_leagues_are_recorded_and_unknown_ones_added(session):
    catalog.refresh(session, opendota([]), NOW)
    assert catalog.record_live(session, live(), NOW) == 2
    amateur, unlisted = session.get(LeagueCatalog, 1003), session.get(LeagueCatalog, 1099)
    assert (amateur.live_games, amateur.live_seen) == (2, NOW)
    assert unlisted.name == "League 1099" and unlisted.live_games == 1  # OpenDota's list lacks it: it gets a row
    assert catalog.status(unlisted, NOW) == "live"


def test_a_league_not_seen_again_stops_being_live(session):
    catalog.record_live(session, live(), NOW)
    league = session.get(LeagueCatalog, 1003)
    assert catalog.status(league, NOW + 14 * 60) == "live"
    catalog.record_live(session, [], NOW + 5 * 60)  # nothing live: the last look stays as it was
    assert league.live_seen == NOW and catalog.status(league, NOW + 16 * 60) == "unknown"


def test_status_uses_the_games_else_liquipedias_end_date(session):
    catalog.refresh(session, opendota([]), NOW)
    assert catalog.status(session.get(LeagueCatalog, 1002), NOW) == "active"
    assert catalog.status(session.get(LeagueCatalog, 1002), NOW + 40 * DAY) == "finished"
    cup = session.get(LeagueCatalog, 1001)
    cup.end_date = "2026-11-30"  # after NOW: still running
    assert catalog.status(cup, NOW) == "active"
    cup.end_date = "2020-01-05"
    assert catalog.status(cup, NOW) == "finished"
    cup.end_date = "2026-11-??"
    assert catalog.status(cup, NOW) == "unknown"


def names(rows: list[dict]) -> list[int]:
    return [r["league_id"] for r in rows]


def test_search_filters_and_sorts(session):
    catalog.refresh(session, opendota([]), NOW)
    session.get(LeagueCatalog, 1001).prize_usd = 1_000_000
    session.get(LeagueCatalog, 1003).prize_usd = 500
    session.commit()
    assert names(catalog.search(session, text="CUP", now=NOW, sort="name")) == [1001, 1004]
    assert names(catalog.search(session, tier="amateur", now=NOW, sort="newest")) == [1004, 1003]  # excluded and none
    assert names(catalog.search(session, tier="premium", now=NOW)) == [1001]
    assert names(catalog.search(session, sort="prize", now=NOW)) == [1001, 1003, 1004, 1002]  # unknown last, newest first
    assert names(catalog.search(session, state="active", now=NOW)) == [1002]
    assert names(catalog.search(session, sort="last", now=NOW))[0] == 1002
    assert names(catalog.search(session, sort="newest", now=NOW, offset=1, limit=2)) == [1003, 1002]


def test_search_text_is_matched_literally(session):
    catalog.refresh(session, opendota([]), NOW)
    assert names(catalog.search(session, text="50%", now=NOW)) == [1004]
    assert catalog.search(session, text="_", now=NOW) == []


def test_search_rows_say_whether_subscribed(session):
    from dotanalyst.db import League

    catalog.refresh(session, opendota([]), NOW)
    session.add(League(league_id=1003, name="Friday Amateur League S9"))
    session.commit()
    rows = {r["league_id"]: r for r in catalog.search(session, now=NOW)}
    assert rows[1003]["subscribed"] and not rows[1002]["subscribed"] and rows[1002]["status"] == "active"


def test_explore_ranks_by_liquipedia_tier_then_prize_then_games(session):
    for i in range(25):  # active leagues
        session.add(LeagueCatalog(league_id=2000 + i, name=f"League {i}", games=i, last_game=NOW - DAY))
    session.add(LeagueCatalog(league_id=1, name="Tier 2", lp_tier=2, prize_usd=10, games=1, last_game=NOW - DAY))
    session.add(LeagueCatalog(league_id=2, name="Tier 1 small", lp_tier=1, prize_usd=10, games=1, last_game=NOW - DAY))
    session.add(LeagueCatalog(league_id=3, name="Tier 1 big", lp_tier=1, prize_usd=900, games=1, last_game=NOW - DAY))
    session.add(LeagueCatalog(league_id=4, name="Over", lp_tier=1, prize_usd=10**6, games=9, last_game=NOW - 60 * DAY))
    session.commit()
    catalog.record_live(session, live(), NOW)
    found = catalog.explore(session, NOW)
    assert names(found["big"])[:4] == [3, 2, 1, 2024] and len(found["big"]) == 20
    assert names(found["live"]) == [1003, 1099]  # most live games first


def test_live_step_records_the_live_leagues(session, monkeypatch, tmp_path):
    from dotanalyst import poll, steam

    monkeypatch.setattr(steam, "PAUSE", 0)
    asked = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return httpx.Response(200, content=(FIXTURES / "steam_live.json").read_bytes())

    setup = poll.Setup("key", None, tmp_path)  # never the real data folder
    assert poll.live_step(session, httpx.Client(transport=httpx.MockTransport(answer)), setup) == 2
    assert asked == ["/IDOTA2Match_570/GetLiveLeagueGames/v1/"] and session.get(LeagueCatalog, 1099).live_games == 1
    assert poll.live_step(session, httpx.Client(transport=httpx.MockTransport(answer)), poll.Setup("", None, tmp_path)) == 0


def test_new_steps_wait_their_own_interval():
    from dotanalyst import poll

    assert poll.wait_after("live") == 300 and poll.wait_after("catalog") == 600


def test_catalog_step_looks_up_explores_and_subscribed_leagues_once(session, tmp_path):
    from dotanalyst import poll
    from dotanalyst.db import League

    session.add(League(league_id=1003, name="Friday Amateur League S9"))
    session.commit()
    wiki: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.host == "liquipedia.net" and "titles" in request.url.params:  # Explore's tournament list: none
            return httpx.Response(200, json={"query": {"pages": {}}})
        if request.url.host == "liquipedia.net":
            wiki.append(request.url.params["gsrsearch"])
            return httpx.Response(200, content=(FIXTURES / "lp_none.json").read_bytes())
        if request.url.path == "/api/explorer":
            return httpx.Response(200, content=(FIXTURES / "od_explorer.json").read_bytes())
        return httpx.Response(200, content=(FIXTURES / "od_leagues.json").read_bytes())

    client = httpx.Client(transport=httpx.MockTransport(answer))
    assert poll.catalog_step(session, client, poll.Setup("", None, tmp_path), NOW) == 3
    # active, subscribed, and a pro league with no game yet (Explore's starting soon)
    assert sorted(wiki) == ['insource:"leagueid=1001"', 'insource:"leagueid=1002"', 'insource:"leagueid=1003"']
    assert poll.catalog_step(session, client, poll.Setup("", None, tmp_path), NOW + 60) == 0 and len(wiki) == 3


def test_region_from_infobox_region_then_country():
    assert catalog.region_of("Europe", "") == "Europe"
    assert catalog.region_of("Southeast Asia", "") == "SEA"
    assert catalog.region_of("", "Peru") == "South America"
    assert catalog.region_of("", "Russia") == "CIS"
    assert catalog.region_of("World", "") == "International"
    assert catalog.region_of("", "Europe") == "Europe"  # Liquipedia writes a region as the country too


def test_region_none_is_kept_as_empty():
    assert catalog.region_of("", "") == "" and catalog.region_of("Atlantis", "Narnia") == ""
