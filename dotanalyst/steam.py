import logging
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Account, Hero, Item, Match, MatchPlayer

BASE = "https://api.steampowered.com"
HISTORY = "IDOTA2Match_570/GetMatchHistory/V001/"
# GetMatchDetails is broken on Valve's side; a sequence query for exactly one match replaces it
DETAILS = "IDOTA2Match_570/GetMatchHistoryBySequenceNum/V001/"
HEROES = "IEconDOTA2_570/GetHeroes/v1/"
ITEM_IDS = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/item_ids.json"
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
    return response.json()["result"]


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
            found = call(
                client, key, DETAILS, start_at_match_seq_num=entry["match_seq_num"], matches_requested=1
            ).get("matches", [])
            if not found or found[0]["match_id"] != entry["match_id"]:
                logging.warning("no details for match %s, will retry on the next sync", entry["match_id"])
                continue
            store_match(session, found[0])
            session.commit()  # per match, so an interrupted backfill keeps its progress
            new += 1
        result[account.account_id] = new
    return result


def sync_constants(session: Session, client: httpx.Client, key: str) -> tuple[int, int]:
    """Store hero and item names. Returns how many of each."""
    heroes = call(client, key, HEROES, language="en")["heroes"]
    for h in heroes:
        session.merge(Hero(id=h["id"], name=h["name"], localized_name=h["localized_name"]))
    # the Web API has no working item list; this file maps item id to internal name
    response = client.get(ITEM_IDS, timeout=30)
    if response.status_code != 200:
        raise SteamError(f"item names: HTTP {response.status_code}")
    items = response.json()
    for item_id, name in items.items():
        session.merge(Item(id=int(item_id), name=name))
    session.commit()
    return len(heroes), len(items)
