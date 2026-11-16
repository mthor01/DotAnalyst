import copy
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from dotanalyst import steam
from dotanalyst.db import Ability, Account, Base, Hero, Item, LeagueMatch, Match, MatchPlayer, PlayerName, Recipe

FIXTURES = Path(__file__).parent / "fixtures"
ME = 2003
KEY = "SECRETKEY"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


PAGE1, PAGE2, DETAILS, HEROES = (
    load(n) for n in ("history_page1.json", "history_page2.json", "details_by_seq.json", "heroes.json")
)
ITEM_IDS = load("item_ids.json")
ITEMS = load("items.json")  # eleven items cut from dotaconstants' items.json
ABILITIES = load("abilities.json")  # six abilities cut from dotaconstants' abilities.json
CONSTANTS = {"item_ids.json": ITEM_IDS, "items.json": ITEMS, "abilities.json": ABILITIES}
EMPTY_PAGE ={"result": {"status": 1, "num_results": 0, "results_remaining": 0, "matches": []}}
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
        if request.url.host != "api.steampowered.com":
            assert "key" not in params  # the key must never go to another host
            return httpx.Response(200, json=CONSTANTS[request.url.path.rsplit("/", 1)[-1]])
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


def test_a_newest_only_sync_stops_at_a_page_that_is_all_stored(session):
    steam.sync(session, FakeSteam().client, KEY)
    fake = FakeSteam()
    assert steam.sync(session, fake.client, KEY, newest_only=True) == {ME: 0}
    assert fake.count("GetMatchHistory/") == 1  # a full sync reads all 3 pages again


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


def test_sync_constants_stores_heroes_and_items(session):
    counts = steam.sync_constants(session, FakeSteam().client, KEY)
    assert counts == (len(HEROES["result"]["heroes"]), len(ITEM_IDS))
    assert session.get(Hero, 1).name == "npc_dota_hero_antimage"
    assert session.get(Item, 1).name == "blink"
    assert session.get(Recipe, "power_treads").components == ["boots", "gloves", "belt_of_strength"]
    assert session.get(Recipe, "sphere").components == ["pers", "ultimate_orb"]  # the scroll, listed as "", is dropped
    assert session.get(Recipe, "boots") is None  # bought whole
    assert session.get(Ability, "luna_lucent_beam").dname == "Lucent Beam"
    assert session.get(Ability, "special_bonus_attack_speed_20").dname == "+20 Attack Speed"
    assert session.get(Ability, "generic_hidden") is None  # the game shows no name for it
    # dotaconstants left this talent's number as {s:bonus_healing_ward_bonus_health}
    assert session.get(Ability, "special_bonus_unique_juggernaut_2").dname == "+? Healing Ward Hits to Kill"
    assert steam.sync_constants(session, FakeSteam().client, KEY) == counts  # rerun replaces, no duplicates
    assert len(session.scalars(select(Recipe)).all()) == 5


LEAGUE_PAGE, LEAGUE_DETAILS = load("league_history.json"), load("league_details.json")  # three games of league 18795
LEAGUE_GAMES = LEAGUE_PAGE["result"]["matches"]
# Steam says results_remaining 0 on a page that has more behind it: this game is only on the page after
LATER_GAME = {**LEAGUE_GAMES[0], "match_id": 8568000000, "match_seq_num": 7196000000}
RECORDED = 8568399403  # the game league_details.json was recorded from
NO_PROFILE = 1010  # Steam leaves an account without a profile out of its answer


class FakeLeague:
    """Steam's answers about league 18795: two pages of games, the recorded details for each, and player names."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self.handle))

    def count(self, method: str) -> int:
        return sum(method in r.url.path for r in self.requests)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params = request.url.params
        assert params["key"] == KEY
        if "GetPlayerSummaries" in request.url.path:
            accounts = [int(i) - steam.STEAM_ID_BASE for i in params["steamids"].split(",")]
            assert len(accounts) <= 100
            players = [{"steamid": str(a + steam.STEAM_ID_BASE), "personaname": f"player {a}"} for a in accounts]
            return httpx.Response(200, json={"response": {"players": [p for p in players if "1010" not in p["personaname"]]}})
        if "GetMatchHistoryBySequenceNum" in request.url.path:
            seq = int(params["start_at_match_seq_num"])
            entry = next(e for e in [*LEAGUE_GAMES, LATER_GAME] if e["match_seq_num"] == seq)
            body = copy.deepcopy(LEAGUE_DETAILS)
            body["result"]["matches"][0].update(match_seq_num=seq, match_id=entry["match_id"])
            return httpx.Response(200, json=body)
        if params["league_id"] != "18795":
            return httpx.Response(200, json=EMPTY_PAGE)
        start = params.get("start_at_match_id")
        if start is None:
            return httpx.Response(200, json=LEAGUE_PAGE)
        if int(start) == LEAGUE_GAMES[-1]["match_id"] - 1:
            return httpx.Response(200, json={"result": {"status": 1, "results_remaining": 0, "matches": [LATER_GAME]}})
        return httpx.Response(200, json=EMPTY_PAGE)


def test_league_sync_stores_each_game_with_its_teams_and_draft(session):
    assert steam.sync_leagues(session, FakeLeague().client, KEY) == 4
    game = session.get(LeagueMatch, RECORDED)
    assert (game.league_id, game.start_time, game.radiant_win) == (18795, 1763665760, False)
    assert (game.radiant_team_id, game.radiant_name) == (9906479, "Sayonara")
    assert (game.dire_team_id, game.dire_name) == (9635282, "New Kidz Doto")
    assert len(game.raw_json["picks_bans"]) == 24 and len(game.raw_json["players"]) == 10


def test_league_sync_reads_on_past_a_page_that_says_nothing_remains(session):
    steam.sync_leagues(session, FakeLeague().client, KEY)
    assert session.get(LeagueMatch, LATER_GAME["match_id"]) is not None


def test_league_games_stay_out_of_the_accounts_matches(session):
    """The poller decides which league games become matches (recent ones, for their replays); the sync adds none."""
    steam.sync_leagues(session, FakeLeague().client, KEY)
    assert session.scalar(select(func.count()).select_from(Match)) == 0


def test_second_league_sync_fetches_no_details(session):
    steam.sync_leagues(session, FakeLeague().client, KEY)
    fake = FakeLeague()
    assert steam.sync_leagues(session, fake.client, KEY) == 0
    assert fake.count("GetMatchHistoryBySequenceNum") == 0


def test_a_newest_only_league_sync_stops_at_a_page_that_is_all_stored(session):
    steam.sync_leagues(session, FakeLeague().client, KEY)
    fake = FakeLeague()
    assert steam.sync_leagues(session, fake.client, KEY, newest_only=True) == 0
    assert fake.count("GetMatchHistory/") == len(steam.LEAGUES)  # one page each; a full sync reads 2 more
    assert fake.count("GetPlayerSummaries") == 0  # no new game, no new player


def test_league_sync_stores_the_players_steam_names(session):
    steam.sync_leagues(session, FakeLeague().client, KEY)
    assert session.get(PlayerName, 1001).name == "player 1001"
    assert session.get(PlayerName, NO_PROFILE) is None
    assert session.scalar(select(func.count()).select_from(PlayerName)) == 9
