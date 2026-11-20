"""A league player's last games outside the league, from OpenDota: the basic numbers, and for the players of a
checked team the match itself, so that the poller can fetch its replay."""
import threading
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import LeagueMatch, PlayerGame, PlayerGameList
from .steam import ANONYMOUS, STATS

PLAYER_MATCHES = "https://api.opendota.com/api/players/{}/matches"
LEAGUE = "https://api.opendota.com/api/leagues/{}"
GAMES = 100  # kept per player
ASKED = 150  # asked for, so that dropping the league and lobby games still leaves GAMES
LEAGUE_LOBBIES = (1, 2)  # practice and tournament: league games, of this league or another
FIELDS = ("hero_id", "player_slot", "radiant_win", "start_time", "lobby_type", "game_mode", "kills", "deaths",
          "assists", "lane_role")  # fmt: skip
PAUSE = 1.0  # seconds between OpenDota calls, from whatever thread: it allows 60 a minute
_paced = {"last": 0.0}
_pace_lock = threading.Lock()


def pace() -> None:
    """Wait until PAUSE has passed since the last OpenDota call. Call it right before each one."""
    with _pace_lock:
        time.sleep(max(0.0, _paced["last"] + PAUSE - time.monotonic()))
        _paced["last"] = time.monotonic()


def unlisted_players(session: Session, n: int) -> list[int]:
    """Up to n league players whose games outside the league were never asked for, those of the newest games first."""
    listed = set(session.scalars(select(PlayerGameList.account_id)))
    found: list[int] = []
    for raw in session.scalars(select(LeagueMatch.raw_json).order_by(LeagueMatch.start_time.desc())):
        for p in raw.get("players", []):
            account_id = p.get("account_id")
            if account_id not in (None, ANONYMOUS) and account_id not in listed and account_id not in found:
                found.append(account_id)
                if len(found) == n:
                    return found
    return found


def league_name(client: httpx.Client, league_id: int) -> str | None:
    """A tournament's name, from OpenDota. None when it does not know the league or does not answer."""
    try:
        pace()
        response = client.get(LEAGUE.format(league_id), timeout=30)
        body = response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None
    name = body.get("name") if isinstance(body, dict) else None
    if not isinstance(name, str):
        return None
    return name.strip() or None


def fetch_player_games(session: Session, client: httpx.Client, account_id: int) -> int:
    """Store a player's last GAMES games outside the league, once: a listed player is never asked for again.
    Returns how many were stored. A player who hides their games gets an empty list, and is listed all the same.
    An HTTP error or a status other than 200 raises httpx.HTTPError, and the player stays unlisted."""
    if session.get(PlayerGameList, account_id) is not None:
        return 0
    return store_player_games(session, account_id, player_games(client, account_id))


def player_games(client: httpx.Client, account_id: int) -> list:
    """OpenDota's list of a player's last games. Touches no database, so it runs on any thread."""
    params = {"limit": ASKED, "significant": 0, "project": FIELDS}
    pace()
    response = client.get(PLAYER_MATCHES.format(account_id), params=params, timeout=30)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise httpx.HTTPError(f"OpenDota sent {type(rows).__name__} for the games of {account_id}, not a list")
    return rows


def store_player_games(session: Session, account_id: int, rows: list) -> int:
    """Keep up to GAMES of player_games' rows outside the league and list the player. Returns how many were kept."""
    ids = [r.get("match_id") for r in rows if isinstance(r, dict)]
    league = set(session.scalars(select(LeagueMatch.match_id).where(LeagueMatch.match_id.in_(ids))))
    kept = 0
    for r in rows:
        if kept == GAMES:
            break
        if not _valid(r) or r["match_id"] in league or r.get("lobby_type") in LEAGUE_LOBBIES:
            continue
        number = lambda key: r.get(key) if isinstance(r.get(key), int) else None  # noqa: E731
        session.merge(
            PlayerGame(
                account_id=account_id, match_id=r["match_id"], start_time=r["start_time"], hero_id=r["hero_id"],
                player_slot=r["player_slot"], radiant_win=r["radiant_win"], lobby_type=number("lobby_type"),
                game_mode=number("game_mode"), kills=number("kills"), deaths=number("deaths"),
                assists=number("assists"), lane_role=number("lane_role"),
            )
        )  # fmt: skip
        kept += 1
    session.add(PlayerGameList(account_id=account_id, fetched_at=int(time.time())))
    session.commit()
    return kept


def _valid(r) -> bool:
    """A row with what every game needs, in the types the tables take."""
    ints = ("match_id", "start_time", "hero_id", "player_slot")
    return isinstance(r, dict) and all(isinstance(r.get(k), int) for k in ints) and isinstance(r.get("radiant_win"), bool)


MATCH_KEYS = ("match_id", "match_seq_num", "start_time", "duration", "game_mode", "lobby_type", "cluster")
PLAYER_KEYS = ("player_slot", "hero_id", "account_id", *(f"item_{i}" for i in range(6)), "item_neutral", *STATS)


def usual_match(found: dict | None, match_id: int) -> dict | None:
    """OpenDota's answer for a match cut down to what Steam's match details hold, so that it is stored like those;
    None when it lacks what a match needs. The cluster goes into the replay's URL, so only a number passes."""
    if not isinstance(found, dict) or found.get("match_id") != match_id:
        return None
    if not all(type(found.get(k)) is int for k in MATCH_KEYS) or not isinstance(found.get("players"), list):
        return None
    players = found["players"]
    if not all(isinstance(p, dict) and type(p.get("player_slot")) is int and type(p.get("hero_id")) is int for p in players):
        return None
    return {
        **{k: found[k] for k in MATCH_KEYS}, "radiant_win": bool(found.get("radiant_win")),
        "players": [{k: p[k] for k in PLAYER_KEYS if k in p} for p in players],
    }  # fmt: skip
