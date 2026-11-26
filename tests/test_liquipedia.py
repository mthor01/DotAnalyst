"""Prize pool, tier, dates and place of a league from Liquipedia's wiki, found by its league id."""
import json
import threading
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst import liquipedia
from dotanalyst.db import Base, Derived, LeagueCatalog

FIXTURES = Path(__file__).parent / "fixtures"
NOW = 1_795_100_000
DAY = 86400


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def wiki(asked: list[httpx.Request], fixture: str) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return httpx.Response(200, content=(FIXTURES / fixture).read_bytes())

    return httpx.Client(transport=httpx.MockTransport(answer))


def test_infobox_reads_the_fields():
    text = json.loads((FIXTURES / "lp_found.json").read_text(encoding="utf-8"))["query"]["pages"]["501"]["revisions"][0]
    assert liquipedia.infobox(text["slots"]["main"]["*"]) == {
        "lp_tier": 3, "prize_usd": 50000, "start_date": "2026-11-07", "end_date": "2026-11-20", "location": "Jönköping, Sweden",
    }  # fmt: skip


def test_infobox_survives_odd_values():
    box = "{{Infobox league\n|liquipediatier=Qualifier\n|prizepoolusd=TBA\n|sdate=2026-11-??\n|type=Online\n|country=Europe\n}}"
    assert liquipedia.infobox(box) == {"lp_tier": None, "prize_usd": None, "start_date": None, "end_date": None, "location": "Online, Europe"}
    assert liquipedia.infobox("no infobox here") == dict.fromkeys(("lp_tier", "prize_usd", "start_date", "end_date", "location"))
    assert liquipedia.infobox("{{Infobox league\n|prizepoolusd=$1,600,000.00\n|liquipediatier=1}}")["prize_usd"] == 1600000


def test_lookup_stores_a_found_page_and_sends_the_agent(session):
    session.add(LeagueCatalog(league_id=1001, name="Grand Cup 2026"))
    asked: list[httpx.Request] = []
    assert liquipedia.lookup(session, wiki(asked, "lp_found.json"), 1001, NOW)
    (request,) = asked
    assert request.headers["User-Agent"] == liquipedia.AGENT and "github.com/mthor01/DotAnalyst" in liquipedia.AGENT
    assert request.url.params["gsrsearch"] == 'insource:"leagueid=1001"'
    row = session.get(LeagueCatalog, 1001)
    assert (row.lp_page, row.lp_tier, row.prize_usd, row.end_date, row.lp_checked) == ("Grand Cup/2026", 3, 50000, "2026-11-20", NOW)


def test_a_miss_is_kept_and_not_asked_again_for_a_week(session):
    session.add(LeagueCatalog(league_id=1003, name="Friday Amateur League S9", last_game=NOW - DAY))
    assert not liquipedia.lookup(session, wiki([], "lp_none.json"), 1003, NOW)
    row = session.get(LeagueCatalog, 1003)
    assert row.lp_checked == NOW and row.lp_page is None
    assert not liquipedia.due(row, NOW + 6 * DAY)
    assert liquipedia.due(row, NOW + 8 * DAY)  # still playing: asked again, a page may have come
    row.last_game = NOW - 90 * DAY
    assert not liquipedia.due(row, NOW + 8 * DAY)  # finished: never again


def test_a_league_liquipedia_was_never_asked_about_is_due(session):
    assert liquipedia.due(LeagueCatalog(league_id=1, name="x"), NOW)


def test_a_failed_request_changes_nothing(session):
    session.add(LeagueCatalog(league_id=1001, name="Grand Cup 2026"))
    broken = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    assert not liquipedia.lookup(session, broken, 1001, NOW)
    assert session.get(LeagueCatalog, 1001).lp_checked is None


def test_lookups_keep_two_seconds_apart(monkeypatch):
    monkeypatch.setattr(liquipedia, "PAUSE", 0.05)
    monkeypatch.setitem(liquipedia._paced, "last", 0.0)
    start = time.monotonic()
    threads = [threading.Thread(target=liquipedia.pace) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert time.monotonic() - start >= 0.1
