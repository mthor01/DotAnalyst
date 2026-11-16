"""A league player's last games outside the league, from OpenDota: the basic numbers only, never the replays."""
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import LeagueMatch, PlayerGame, PlayerGameList
from .steam import ANONYMOUS

PLAYER_MATCHES = "https://api.opendota.com/api/players/{}/matches"
GAMES = 100  # kept per player
ASKED = 150  # asked for, so that dropping the league and lobby games still leaves GAMES
LEAGUE_LOBBIES = (1, 2)  # practice and tournament: league games, of this league or another
FIELDS = ("hero_id", "player_slot", "radiant_win", "start_time", "lobby_type", "game_mode", "kills", "deaths",
          "assists", "lane_role")  # fmt: skip


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


def fetch_player_games(session: Session, client: httpx.Client, account_id: int) -> int:
    """Store a player's last GAMES games outside the league, once: a listed player is never asked for again.
    Returns how many were stored. A player who hides their games gets an empty list, and is listed all the same.
    An HTTP error or a status other than 200 raises httpx.HTTPError, and the player stays unlisted."""
    if session.get(PlayerGameList, account_id) is not None:
        return 0
    params = {"limit": ASKED, "significant": 0, "project": FIELDS}
    response = client.get(PLAYER_MATCHES.format(account_id), params=params, timeout=30)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise httpx.HTTPError(f"OpenDota sent {type(rows).__name__} for the games of {account_id}, not a list")
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
