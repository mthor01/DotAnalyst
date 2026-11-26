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
        "region": "Europe",
    }  # fmt: skip


def test_infobox_survives_odd_values():
    box = "{{Infobox league\n|liquipediatier=Qualifier\n|prizepoolusd=TBA\n|sdate=2026-11-??\n|type=Online\n|country=Europe\n}}"
    assert liquipedia.infobox(box) == {"lp_tier": None, "prize_usd": None, "start_date": None, "end_date": None, "location": "Online, Europe", "region": "Europe"}
    assert liquipedia.infobox("no infobox here") == {**dict.fromkeys(("lp_tier", "prize_usd", "start_date", "end_date", "location")), "region": ""}
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


def structure_client(asked: list[httpx.Request], fail: bool = False) -> httpx.Client:
    """Liquipedia's subpage list, the event page with its subpages in one answer, and the commons bracket layout."""

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        if fail:
            return httpx.Response(500)
        if request.url.host == "liquipedia.net" and request.url.path.startswith("/commons/"):
            return httpx.Response(200, content=(FIXTURES / "lp_layout.json").read_bytes())
        if request.url.params.get("list") == "allpages":
            return httpx.Response(200, content=(FIXTURES / "lp_allpages.json").read_bytes())
        return httpx.Response(200, content=(FIXTURES / "lp_pages.json").read_bytes())

    return httpx.Client(transport=httpx.MockTransport(answer))


def row() -> LeagueCatalog:
    return LeagueCatalog(league_id=1002, name="Pro Series 5", lp_page="Pro Series 5", lp_checked=NOW)


def test_structure_fetches_pages_and_layouts_once(tmp_path):
    asked: list[httpx.Request] = []
    found = liquipedia.structure(structure_client(asked), row(), tmp_path, NOW, finished=False)
    assert len(asked) == 3 and found["brackets"][0]["title"] == "Playoffs"
    titles = asked[1].url.params["titles"].split("|")
    assert titles == ["Pro Series 5", "Pro Series 5/Playoffs", "Pro Series 5/Region"]  # no Statistics, nothing deeper
    assert any(m["time"] and m["opponents"] == ["Team A", "Team B"] for m in found["upcoming"])  # from the subpage
    liquipedia.structure(structure_client(asked), row(), tmp_path, NOW + 5 * 3600, finished=False)
    assert len(asked) == 3  # within 6 hours: from data/leagues/1002.lp.json
    liquipedia.structure(structure_client(asked), row(), tmp_path, NOW + 7 * 3600, finished=False)
    assert len(asked) == 5  # pages again, the layout not: it never changes
    liquipedia.structure(structure_client(asked), row(), tmp_path, NOW + 90 * DAY, finished=True)
    assert len(asked) == 5


def test_a_qualifier_child_is_dropped(tmp_path):
    found = liquipedia.structure(structure_client([]), row(), tmp_path, NOW, finished=False)
    assert [g["title"] for g in found["groups"]] == ["Group A"]  # not Group Q of the Region qualifier (league 1999)


def test_a_failed_refresh_keeps_the_old_structure(tmp_path):
    old = liquipedia.structure(structure_client([]), row(), tmp_path, NOW, finished=False)
    asked: list[httpx.Request] = []
    again = liquipedia.structure(structure_client(asked, fail=True), row(), tmp_path, NOW + 7 * 3600, finished=False)
    assert asked and again == old
    assert liquipedia.structure(structure_client([], fail=True), row(), tmp_path / "empty", NOW, finished=False) is None


def test_empty_bracket_slots_are_read_from_their_match_pages(tmp_path):
    from tests.test_lp_structure import MATCH_PAGE, NEW_STYLE

    def revisions(pages: dict) -> dict:
        return {"query": {"pages": {str(i): {"title": t, "revisions": [{"slots": {"main": {"*": x}}}]} for i, (t, x) in enumerate(pages.items())}}}

    asked: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        if request.url.params.get("list") == "allpages":
            return httpx.Response(200, json={"query": {"allpages": []}})
        if "Match:ID" in request.url.params.get("titles", ""):
            return httpx.Response(200, json=revisions({"Match:ID QQQQ R01-M001": MATCH_PAGE}))
        return httpx.Response(200, json=revisions({"Pro Series 6": NEW_STYLE}))

    found = liquipedia.pages(httpx.Client(transport=httpx.MockTransport(answer)), "Pro Series 6", 1002)
    assert len(asked) == 3 and asked[2].url.params["titles"] == "Match:ID QQQQ R01-M001"
    assert set(found) == {"Pro Series 6", "Match:ID QQQQ R01-M001"}


def test_a_structure_kept_by_an_older_version_is_read_again(tmp_path):
    (tmp_path / "leagues").mkdir()
    (tmp_path / "leagues" / "1002.lp.json").write_text(json.dumps({"fetched": NOW, "page": "Pro Series 5", "found": {}}))
    asked: list[httpx.Request] = []
    found = liquipedia.structure(structure_client(asked), row(), tmp_path, NOW, finished=True)
    assert asked and found["brackets"]


def test_infobox_reads_region():
    assert liquipedia.infobox("{{Infobox league\n|country=Germany\n|type=Offline\n}}")["region"] == "Europe"
    assert liquipedia.infobox("{{Infobox league\n|region=Southeast Asia\n|country=Singapore\n}}")["region"] == "SEA"
