import json
import logging
import re
import threading
import time
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import DATA, Ability, Account, Hero, Item, League, LeagueMatch, Match, MatchPlayer, PlayerName, Recipe

BASE = "https://api.steampowered.com"
HISTORY = "IDOTA2Match_570/GetMatchHistory/V001/"
# GetMatchDetails is broken on Valve's side; a sequence query for exactly one match replaces it
DETAILS = "IDOTA2Match_570/GetMatchHistoryBySequenceNum/V001/"
HEROES = "IEconDOTA2_570/GetHeroes/v1/"
NAMES = "ISteamUser/GetPlayerSummaries/v2/"
LOGO = "ISteamRemoteStorage/GetUGCFileDetails/v1/"
STEAM_ID_BASE = 76561197960265728  # a 64-bit Steam id is this plus the 32-bit account id
ITEM_IDS = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/item_ids.json"
ITEMS = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/items.json"
ABILITIES = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/abilities.json"
HERO_FILE = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/heroes.json"
PAUSE = 1.0  # seconds between Steam calls, from whatever thread: the poll steps call it side by side
_paced = {"last": 0.0}
_pace_lock = threading.Lock()
ANONYMOUS = 4294967295
HISTORY_NOT_EXPOSED = 15
STATS = (
    "kills", "deaths", "assists", "last_hits", "denies", "gold_per_min", "xp_per_min",
    "net_worth", "level", "hero_damage", "tower_damage", "hero_healing", "leaver_status",
)


class SteamError(Exception):
    pass


def pace() -> None:
    """Wait until PAUSE has passed since the last Steam call. Call it right before each one."""
    with _pace_lock:
        time.sleep(max(0.0, _paced["last"] + PAUSE - time.monotonic()))
        _paced["last"] = time.monotonic()


def call(client: httpx.Client, key: str, path: str, **params) -> dict:
    pace()
    try:
        response = client.get(f"{BASE}/{path}", params={"key": key, **params}, timeout=30)
    except httpx.HTTPError as error:
        # httpx messages contain the URL, and the URL contains the key
        raise SteamError(f"{path}: {type(error).__name__}") from None
    if response.status_code != 200:
        raise SteamError(f"{path}: HTTP {response.status_code}")
    body = response.json()
    return body["result"] if "result" in body else body["response"]  # ISteamUser answers under "response"


def match_history(client: httpx.Client, key: str, account_id: int, known: set[int] = frozenset()) -> list[dict] | None:
    """Up to 500 most recent matches, or None when the account does not expose its history.

    Paging stops early at a page whose matches are all in known: everything older was read before.
    """
    matches: list[dict] = []
    params = {"account_id": account_id, "matches_requested": 100}
    while True:
        result = call(client, key, HISTORY, **params)
        if result["status"] == HISTORY_NOT_EXPOSED:
            return None
        page = result.get("matches", [])
        matches += page
        # results_remaining can stay above 0 forever (omitted high-rank matches), so an empty page also ends it
        if not page or result.get("results_remaining", 0) <= 0 or all(e["match_id"] in known for e in page):
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


def match_rows(m: dict) -> tuple[Match, list[MatchPlayer]]:
    """The rows one match of the Web API becomes, not stored yet."""
    match = Match(
        match_id=m["match_id"], match_seq_num=m["match_seq_num"], start_time=m["start_time"],
        duration=m["duration"], radiant_win=bool(m.get("radiant_win")), game_mode=m["game_mode"],
        lobby_type=m["lobby_type"], cluster=m["cluster"], raw_json=m,
    )  # fmt: skip
    players = [
        MatchPlayer(
            match_id=m["match_id"], player_slot=p["player_slot"], hero_id=p["hero_id"],
            account_id=None if p.get("account_id") in (None, ANONYMOUS) else p["account_id"],
            items=[p.get(f"item_{i}", 0) for i in range(6)] + [p.get("item_neutral", 0)],
            **{stat: p.get(stat) for stat in STATS},
        )
        for p in m["players"]
    ]
    return match, players


def store_match(session: Session, m: dict) -> None:
    match, players = match_rows(m)
    session.add_all([match, *players])


def sync(session: Session, client: httpx.Client, key: str, newest_only: bool = False) -> dict[int, int | None]:
    """Store new matches of every active account. Returns new matches per account, None if not exposed.

    newest_only reads an account's history only down to a page that is all stored (1 request instead of 5 when
    nothing is new); a full read also finds what an interrupted sync left out further down.
    """
    store_avatars(session, client, key)
    known = set(session.scalars(select(Match.match_id))) if newest_only else frozenset()
    result: dict[int, int | None] = {}
    for account in session.scalars(select(Account).where(Account.active)).all():
        history = match_history(client, key, account.account_id, known)
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


def store_avatars(session: Session, client: httpx.Client, key: str) -> None:
    """Ask Steam once for the profile picture of each active account that has none stored."""
    missing = session.scalars(select(Account).where(Account.active, Account.avatar.is_(None))).all()[:100]
    if not missing:
        return
    steam_ids = ",".join(str(a.account_id + STEAM_ID_BASE) for a in missing)
    found = {int(p["steamid"]) - STEAM_ID_BASE: p for p in call(client, key, NAMES, steamids=steam_ids)["players"]}
    for account in missing:
        profile = found.get(account.account_id, {})
        account.avatar = profile.get("avatarmedium", "")  # "" so an account without a profile is not asked again
        account.label = account.label or profile.get("personaname")  # one added on the site comes without a name
    session.commit()


def store_league_match(session: Session, m: dict) -> None:
    session.add(
        LeagueMatch(
            match_id=m["match_id"], league_id=m["leagueid"], start_time=m["start_time"],
            radiant_team_id=m.get("radiant_team_id", 0), dire_team_id=m.get("dire_team_id", 0),
            radiant_name=m.get("radiant_name"), dire_name=m.get("dire_name"),
            radiant_win=bool(m.get("radiant_win")), raw_json=m,
        )
    )


def leagues(session: Session) -> dict[int, str]:
    """The tracked tournaments by id, oldest id first. A new database tracks none: they are added on the site."""
    return dict(session.execute(select(League.league_id, League.name).order_by(League.league_id)).all())


def sync_leagues(session: Session, client: httpx.Client, key: str, newest_only: bool = False) -> int:
    """Store the games of the tracked tournaments that are not stored yet, and their players' Steam names and pictures. Returns the new games.

    Only the newest 500 games of a league can be listed, see the shortcut below. newest_only stops reading a league
    at a page whose games are all stored.
    """
    new = 0
    for league_id in leagues(session):  # one added since the last poll has nothing stored, so it is read in full
        params = {"league_id": league_id}
        while True:
            # read until a page is empty: results_remaining counts series and reaches 0 with games still to come
            page = call(client, key, HISTORY, **params).get("matches", [])
            if not page or newest_only and all(session.get(LeagueMatch, e["match_id"]) for e in page):
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
    # names stored before pictures were: asked once more, for the picture
    no_picture = {n.account_id: n for n in session.scalars(select(PlayerName).where(PlayerName.avatar.is_(None)))}
    if newest_only and not new and not no_picture:
        return 0  # no new players to name, and reading every stored game each minute is not free
    players = {p.get("account_id") for raw in session.scalars(select(LeagueMatch.raw_json)) for p in raw["players"]}
    unnamed = players - {None, ANONYMOUS} - set(session.scalars(select(PlayerName.account_id)))
    store_names(session, client, key, sorted(unnamed | no_picture.keys()))
    return new


def store_names(session: Session, client: httpx.Client, key: str, account_ids: list[int]) -> None:
    """Ask Steam for these players' names and pictures and store them; a player with a stored name gets the picture."""
    stored = {n.account_id: n for n in session.scalars(select(PlayerName).where(PlayerName.account_id.in_(account_ids)))}
    for i in range(0, len(account_ids), 100):  # Steam takes 100 ids in one request
        steam_ids = ",".join(str(a + STEAM_ID_BASE) for a in account_ids[i : i + 100])
        for p in call(client, key, NAMES, steamids=steam_ids)["players"]:
            account_id, avatar = int(p["steamid"]) - STEAM_ID_BASE, p.get("avatarmedium", "")
            if account_id in stored:
                stored[account_id].avatar = avatar
            else:
                session.add(PlayerName(account_id=account_id, name=p["personaname"], avatar=avatar))
        for account_id in account_ids[i : i + 100]:
            if account_id in stored and stored[account_id].avatar is None:
                stored[account_id].avatar = ""  # Steam has no profile now: not asked again
        session.commit()


def sync_constants(session: Session, client: httpx.Client, key: str) -> tuple[int, int]:
    """Store hero, item and ability names, and what each item is built from. Returns how many heroes and items.

    Heroes come from the Web API when there is a key, else from dotaconstants, which needs none.
    """

    def fetch(url: str) -> dict:
        response = client.get(url, timeout=30)
        if response.status_code != 200:
            raise SteamError(f"{url.rsplit('/', 1)[-1]}: HTTP {response.status_code}")
        return response.json()

    heroes = call(client, key, HEROES, language="en")["heroes"] if key else list(fetch(HERO_FILE).values())
    for h in heroes:
        session.merge(Hero(id=h["id"], name=h["name"], localized_name=h["localized_name"]))
    # the Web API has no working item list; these files map item id to internal name, item to its components, and
    # ability to the name the game shows
    items, details, abilities = (fetch(url) for url in (ITEM_IDS, ITEMS, ABILITIES))
    for name, ability in abilities.items():
        if ability.get("dname"):
            # where dotaconstants could not fill in a talent's number it reads "+{s:bonus_duration}s ..."
            session.merge(Ability(name=name, dname=re.sub(r"\{s:\w+\}", "?", ability["dname"])))
    for item_id, name in items.items():
        session.merge(Item(id=int(item_id), name=name))
    for name, detail in details.items():
        components = [c for c in detail.get("components") or [] if c]  # a scroll is listed as ""
        if components:
            session.merge(Recipe(item=name, components=components))
    session.commit()
    return len(heroes), len(items)


def team_logo(client: httpx.Client, key: str, ugc_id: int, data: Path = DATA) -> str | None:
    """The address of a team logo, from the UGC id a league game's details give it (`radiant_logo`, `dire_logo`).

    Every answer, a logo or Steam's "no such file", is kept in data/logos.json and never asked for again. A failed
    request is not kept, so the next page load asks again.
    """
    stored = data / "logos.json"
    known = json.loads(stored.read_text()) if stored.exists() else {}
    if str(ugc_id) in known or not key:
        return known.get(str(ugc_id))
    pace()
    try:
        response = client.get(f"{BASE}/{LOGO}", params={"key": key, "appid": 570, "ugcid": ugc_id}, timeout=30)
    except httpx.HTTPError:
        return None
    if response.status_code == 200:
        url = (response.json().get("data") or {}).get("url")
        known[str(ugc_id)] = url if isinstance(url, str) and url.startswith("https://") else None
    elif response.status_code == 404:  # an id Steam has no file for
        known[str(ugc_id)] = None
    else:
        return None
    data.mkdir(parents=True, exist_ok=True)
    stored.write_text(json.dumps(known))
    return known[str(ugc_id)]
