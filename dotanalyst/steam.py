import logging
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Account, Hero, Item, LeagueMatch, Match, MatchPlayer, PlayerName, Recipe

BASE = "https://api.steampowered.com"
HISTORY = "IDOTA2Match_570/GetMatchHistory/V001/"
# GetMatchDetails is broken on Valve's side; a sequence query for exactly one match replaces it
DETAILS = "IDOTA2Match_570/GetMatchHistoryBySequenceNum/V001/"
HEROES = "IEconDOTA2_570/GetHeroes/v1/"
NAMES = "ISteamUser/GetPlayerSummaries/v2/"
STEAM_ID_BASE = 76561197960265728  # a 64-bit Steam id is this plus the 32-bit account id
# REINCARNATION - D/A/CH Dota 2 by BEING ESPORTS: the seasons whose games the team pages are built from
LEAGUES = {18795: "Season 6", 19418: "Season 7", 20408: "Season 8"}
ITEM_IDS = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/item_ids.json"
ITEMS = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/items.json"
PAUSE = 1.0  # seconds before every request
ANONYMOUS = 4294967295
HISTORY_NOT_EXPOSED = 15
STATS = (
    "kills", "deaths", "assists", "last_hits", "denies", "gold_per_min", "xp_per_min",
    "net_worth", "level", "hero_damage", "tower_damage", "hero_healing", "leaver_status",
)


class SteamError(Exception):
    pass


def call(client: httpx.Client, key: str, path: str, **params) -> dict:
    time.sleep(PAUSE)
    try:
        response = client.get(f"{BASE}/{path}", params={"key": key, **params}, timeout=30)
    except httpx.HTTPError as error:
        # httpx messages contain the URL, and the URL contains the key
        raise SteamError(f"{path}: {type(error).__name__}") from None
    if response.status_code != 200:
        raise SteamError(f"{path}: HTTP {response.status_code}")
    body = response.json()
    return body["result"] if "result" in body else body["response"]  # ISteamUser answers under "response"


def match_history(client: httpx.Client, key: str, account_id: int) -> list[dict] | None:
    """Up to 500 most recent matches, or None when the account does not expose its history."""
    # shortcut: every sync pages through all 500 (5 requests per account), stop at known matches if that gets costly
    matches: list[dict] = []
    params = {"account_id": account_id, "matches_requested": 100}
    while True:
        result = call(client, key, HISTORY, **params)
        if result["status"] == HISTORY_NOT_EXPOSED:
            return None
        page = result.get("matches", [])
        matches += page
        # results_remaining can stay above 0 forever (omitted high-rank matches), so an empty page also ends it
        if not page or result.get("results_remaining", 0) <= 0:
            return matches
        params["start_at_match_id"] = page[-1]["match_id"] - 1


def details(client: httpx.Client, key: str, entry: dict) -> dict | None:
    """Full data of one match of a history page, or None when Steam does not have it yet."""
    found = call(client, key, DETAILS, start_at_match_seq_num=entry["match_seq_num"], matches_requested=1)
    found = found.get("matches", [])
    if not found or found[0]["match_id"] != entry["match_id"]:
        logging.warning("no details for match %s, will retry on the next sync", entry["match_id"])
        return None
    return found[0]


def store_match(session: Session, m: dict) -> None:
    session.add(
        Match(
            match_id=m["match_id"], match_seq_num=m["match_seq_num"], start_time=m["start_time"],
            duration=m["duration"], radiant_win=bool(m.get("radiant_win")), game_mode=m["game_mode"],
            lobby_type=m["lobby_type"], cluster=m["cluster"], raw_json=m,
        )
    )
    for p in m["players"]:
        account_id = p.get("account_id")
        session.add(
            MatchPlayer(
                match_id=m["match_id"], player_slot=p["player_slot"], hero_id=p["hero_id"],
                account_id=None if account_id in (None, ANONYMOUS) else account_id,
                items=[p.get(f"item_{i}", 0) for i in range(6)] + [p.get("item_neutral", 0)],
                **{stat: p.get(stat) for stat in STATS},
            )
        )


def sync(session: Session, client: httpx.Client, key: str) -> dict[int, int | None]:
    """Store new matches of every active account. Returns new matches per account, None if not exposed."""
    result: dict[int, int | None] = {}
    for account in session.scalars(select(Account).where(Account.active)).all():
        history = match_history(client, key, account.account_id)
        account.history_exposed = history is not None
        session.commit()
        if history is None:
            result[account.account_id] = None
            continue
        new = 0
        for entry in history:
            if session.get(Match, entry["match_id"]) is not None:
                continue  # stored matches are never refetched
            found = details(client, key, entry)
            if found is None:
                continue
            store_match(session, found)
            session.commit()  # per match, so an interrupted backfill keeps its progress
            new += 1
        result[account.account_id] = new
    return result


def store_league_match(session: Session, m: dict) -> None:
    session.add(
        LeagueMatch(
            match_id=m["match_id"], league_id=m["leagueid"], start_time=m["start_time"],
            radiant_team_id=m.get("radiant_team_id", 0), dire_team_id=m.get("dire_team_id", 0),
            radiant_name=m.get("radiant_name"), dire_name=m.get("dire_name"),
            radiant_win=bool(m.get("radiant_win")), raw_json=m,
        )
    )


def sync_leagues(session: Session, client: httpx.Client, key: str) -> int:
    """Store the games of LEAGUES that are not stored yet, and their players' Steam names. Returns the new games.

    Only the newest 500 games of a league can be listed, see the shortcut below.
    """
    new = 0
    for league_id in LEAGUES:
        params = {"league_id": league_id}
        while True:
            # read until a page is empty: results_remaining counts series and reaches 0 with games still to come
            page = call(client, key, HISTORY, **params).get("matches", [])
            if not page:
                break
            for entry in page:
                if session.get(LeagueMatch, entry["match_id"]) is not None:
                    continue  # stored matches are never refetched
                found = details(client, key, entry)
                if found is None:
                    continue
                store_league_match(session, found)
                session.commit()  # per match, so an interrupted backfill keeps its progress
                new += 1
            # shortcut: Steam lists only the newest 500 games of a league (season 7 has 561), and about 1 game in 400
            # falls between two pages; both measured against dota2.com's GetLeagueData. An older game can still be
            # listed with account_id of one of its players next to league_id, if the missing ones are ever wanted
            params["start_at_match_id"] = page[-1]["match_id"] - 1
    players = {p.get("account_id") for raw in session.scalars(select(LeagueMatch.raw_json)) for p in raw["players"]}
    unnamed = sorted(players - {None, ANONYMOUS} - set(session.scalars(select(PlayerName.account_id))))
    for i in range(0, len(unnamed), 100):  # Steam takes 100 ids in one request
        steam_ids = ",".join(str(a + STEAM_ID_BASE) for a in unnamed[i : i + 100])
        for p in call(client, key, NAMES, steamids=steam_ids)["players"]:
            session.add(PlayerName(account_id=int(p["steamid"]) - STEAM_ID_BASE, name=p["personaname"]))
        session.commit()
    return new


def sync_constants(session: Session, client: httpx.Client, key: str) -> tuple[int, int]:
    """Store hero and item names, and what each item is built from. Returns how many heroes and items."""
    heroes = call(client, key, HEROES, language="en")["heroes"]
    for h in heroes:
        session.merge(Hero(id=h["id"], name=h["name"], localized_name=h["localized_name"]))
    # the Web API has no working item list; these files map item id to internal name, and item to its components
    files = []
    for url in (ITEM_IDS, ITEMS):
        response = client.get(url, timeout=30)
        if response.status_code != 200:
            raise SteamError(f"item names: HTTP {response.status_code}")
        files.append(response.json())
    items, details = files
    for item_id, name in items.items():
        session.merge(Item(id=int(item_id), name=name))
    for name, detail in details.items():
        components = [c for c in detail.get("components") or [] if c]  # a scroll is listed as ""
        if components:
            session.merge(Recipe(item=name, components=components))
    session.commit()
    return len(heroes), len(items)
