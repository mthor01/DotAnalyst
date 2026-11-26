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
