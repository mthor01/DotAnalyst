import copy
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from dotanalyst import steam
from dotanalyst.db import Account, Base, Hero, Match, MatchPlayer

FIXTURES = Path(__file__).parent / "fixtures"
ME = 314448639
KEY = "SECRETKEY"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


PAGE1, PAGE2, DETAILS, HEROES = (
    load(n) for n in ("history_page1.json", "history_page2.json", "details_by_seq.json", "heroes.json")
)
EMPTY_PAGE = {"result": {"status": 1, "num_results": 0, "results_remaining": 0, "matches": []}}
NOT_EXPOSED = {"result": {"status": 15, "statusDetail": "Cannot get match history for a user that hasn't allowed it"}}
HISTORY = PAGE1["result"]["matches"] + PAGE2["result"]["matches"]
SEQ_TO_MATCH = {m["match_seq_num"]: m["match_id"] for m in HISTORY}


class FakeSteam:
    """Answers like the Steam Web API from the recorded fixtures and records every request."""

    def __init__(self, history_exposed: bool = True, wrong_details: bool = False):
        self.history_exposed = history_exposed
        self.wrong_details = wrong_details
        self.requests: list[httpx.Request] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self.handle))

    def count(self, method: str) -> int:
        return sum(method in r.url.path for r in self.requests)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params = request.url.params
        assert params["key"] == KEY
        if "GetHeroes" in request.url.path:
            return httpx.Response(200, json=HEROES)
        if "GetMatchHistoryBySequenceNum" in request.url.path:
            assert params["matches_requested"] == "1"
            seq = int(params["start_at_match_seq_num"])
            body = copy.deepcopy(DETAILS)
            body["result"]["matches"][0]["match_seq_num"] = seq
            body["result"]["matches"][0]["match_id"] = 1 if self.wrong_details else SEQ_TO_MATCH[seq]
            return httpx.Response(200, json=body)
        if not self.history_exposed:
            return httpx.Response(200, json=NOT_EXPOSED)
        start = params.get("start_at_match_id")
        if start is None:
            return httpx.Response(200, json=PAGE1)
        if int(start) == PAGE1["result"]["matches"][-1]["match_id"] - 1:
            return httpx.Response(200, json=PAGE2)
        return httpx.Response(200, json=EMPTY_PAGE)


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(steam, "PAUSE", 0)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(account_id=ME))
        s.commit()
        yield s


def test_history_follows_pages_until_empty():
    fake = FakeSteam()
    matches = steam.match_history(fake.client, KEY, ME)
    assert [m["match_id"] for m in matches] == [m["match_id"] for m in HISTORY]
    assert fake.count("GetMatchHistory/") == 3


def test_sync_stores_matches_and_players(session):
    assert steam.sync(session, FakeSteam().client, KEY) == {ME: len(HISTORY)}
    assert session.get(Account, ME).history_exposed is True

    recorded = DETAILS["result"]["matches"][0]
    match = session.get(Match, HISTORY[0]["match_id"])
    assert (match.duration, match.radiant_win, match.game_mode, match.cluster) == (
        recorded["duration"], recorded["radiant_win"], recorded["game_mode"], recorded["cluster"],
    )
    assert match.replay_state == "none"

    players = session.scalars(select(MatchPlayer).where(MatchPlayer.match_id == match.match_id)).all()
    assert len(players) == 10
    assert {p.player_slot for p in players} == {0, 1, 2, 3, 4, 128, 129, 130, 131, 132}
    by_slot = {p["player_slot"]: p for p in recorded["players"]}
    for p in players:
        source = by_slot[p.player_slot]
        assert (p.hero_id, p.kills, p.last_hits, p.gold_per_min) == (
            source["hero_id"], source["kills"], source["last_hits"], source["gold_per_min"],
        )
        assert p.items == [source[f"item_{i}"] for i in range(6)] + [source["item_neutral"]]
        assert p.account_id != steam.ANONYMOUS
    assert ME in {p.account_id for p in players}


def test_anonymous_player_has_no_account_id(session):
    match = copy.deepcopy(DETAILS["result"]["matches"][0])
    match["players"][0]["account_id"] = steam.ANONYMOUS
    del match["players"][1]["account_id"]
    steam.store_match(session, match)
    session.commit()
    slots = {p["player_slot"] for p in match["players"][:2]}
    stored = session.scalars(select(MatchPlayer).where(MatchPlayer.player_slot.in_(slots))).all()
    assert [p.account_id for p in stored] == [None, None]


def test_second_sync_fetches_no_details(session):
    steam.sync(session, FakeSteam().client, KEY)
    fake = FakeSteam()
    assert steam.sync(session, fake.client, KEY) == {ME: 0}
    assert fake.count("GetMatchHistoryBySequenceNum") == 0


def test_unexposed_history_is_flagged_not_an_error(session):
    fake = FakeSteam(history_exposed=False)
    assert steam.sync(session, fake.client, KEY) == {ME: None}
    assert session.get(Account, ME).history_exposed is False
    assert session.scalar(select(func.count()).select_from(Match)) == 0
    assert fake.count("GetMatchHistoryBySequenceNum") == 0


def test_inactive_account_is_skipped(session):
    session.get(Account, ME).active = False
    session.commit()
    fake = FakeSteam()
    assert steam.sync(session, fake.client, KEY) == {}
    assert fake.requests == []


def test_details_for_another_match_are_not_stored(session):
    assert steam.sync(session, FakeSteam(wrong_details=True).client, KEY) == {ME: 0}
    assert session.scalar(select(func.count()).select_from(Match)) == 0


def test_errors_do_not_leak_the_key():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, text="Forbidden")))
    with pytest.raises(steam.SteamError) as error:
        steam.call(client, KEY, steam.HISTORY, account_id=ME)
    assert "403" in str(error.value) and KEY not in str(error.value)

    def unreachable(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(unreachable))
    with pytest.raises(steam.SteamError) as error:
        steam.call(client, KEY, steam.HISTORY, account_id=ME)
    assert KEY not in str(error.value)


def test_sync_constants_stores_heroes(session):
    count = steam.sync_constants(session, FakeSteam().client, KEY)
    assert count == len(HEROES["result"]["heroes"]) > 100
    assert session.get(Hero, 1).name == "npc_dota_hero_antimage"
    assert steam.sync_constants(session, FakeSteam().client, KEY) == count  # rerun replaces, no duplicates
