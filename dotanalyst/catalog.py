"""The tournament browser's list of every league (league_catalog): OpenDota's league list and the dates of the pro
leagues once a day, the leagues playing right now from Steam's live list, and the search and Explore page over it.
See Tournament browser in IMPLEMENTATION.md."""
import calendar
import logging
import time
from collections import Counter

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import League, LeagueCatalog
from .opendota import pace

LEAGUES = "https://api.opendota.com/api/leagues"
EXPLORER = "https://api.opendota.com/api/explorer"
STALE = 86400  # OpenDota's list is read again after a day
ACTIVITY_DAYS = 365  # the explorer counts the pro games of this many days back
LIVE_MINUTES = 15  # a league seen in Steam's live list this recently is live
ACTIVE_DAYS = 30  # a league whose last game is this recent is active, else finished
BIG = 20  # Explore's biggest leagues
SORTS = {  # search order; ties keep the newest league (highest id) first
    "name": lambda r: r["name"].lower(),
    "last": lambda r: -(r["last"] or 0),
    "games": lambda r: -(r["games"] or 0),
    "prize": lambda r: -(r["prize_usd"] or 0),
    "newest": lambda r: 0,
}
log = logging.getLogger(__name__)


def _get(client: httpx.Client, url: str, **params):
    """OpenDota's answer as JSON, None when it fails."""
    pace()
    try:
        response = client.get(url, params=params, timeout=60)
        return response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def refresh(session: Session, client: httpx.Client, now: float | None = None) -> int:
    """Read OpenDota's league list and its pro leagues' games of the last year into the catalog, once a day.
    Rows are only added and updated, never deleted: a league seen live or subscribed stays. Returns the rows added."""
    now = int(now or time.time())
    last = session.scalar(select(func.max(LeagueCatalog.refreshed)))
    if last is not None and now - last < STALE:
        return 0
    listed = _get(client, LEAGUES)
    if not isinstance(listed, list):
        log.warning("OpenDota's league list did not come")
        return 0
    known = {r.league_id: r for r in session.scalars(select(LeagueCatalog))}
    added = 0
    for entry in listed:
        league_id, name = entry.get("leagueid"), (entry.get("name") or "").strip()
        if not isinstance(league_id, int):
            continue
        row = known.get(league_id)
        if row is None:
            row = known[league_id] = LeagueCatalog(league_id=league_id, name=name or f"League {league_id}")
            session.add(row)
            added += 1
        elif name:
            row.name = name
        row.tier, row.refreshed = entry.get("tier"), now
    # the explorer runs SQL on OpenDota's pro matches; amateur leagues are not in them
    sql = (
        "select leagueid, count(*) games, min(start_time) first_at, max(start_time) last_at from matches "
        f"where start_time > {now - ACTIVITY_DAYS * 86400} group by leagueid"
    )  # OpenDota refuses the column names first and last
    found = _get(client, EXPLORER, sql=sql)
    for r in found.get("rows", []) if isinstance(found, dict) else []:
        if (row := known.get(r.get("leagueid"))) is not None:
            row.games, row.first_game, row.last_game = int(r["games"]), int(r["first_at"]), int(r["last_at"])
    session.commit()
    return added


def record_live(session: Session, games: list[dict], now: float) -> int:
    """Note the leagues of Steam's live league games; a league OpenDota's list lacks gets a row of its own.
    A look with no games changes nothing, so a league stays live LIVE_MINUTES after it was last seen."""
    counts = Counter(g["league_id"] for g in games if g.get("league_id"))
    for league_id, n in counts.items():
        row = session.get(LeagueCatalog, league_id)
        if row is None:
            row = LeagueCatalog(league_id=league_id, name=f"League {league_id}")
            session.add(row)
        row.live_games, row.live_seen = n, int(now)
    session.commit()
    return len(counts)


def day_end(date: str | None) -> int | None:
    """The last second of a Liquipedia date, YYYY-MM-DD; None when it is not one (2026-11-??, TBA)."""
    try:
        return calendar.timegm(time.strptime(date, "%Y-%m-%d")) + 86399 if date else None
    except ValueError:
        return None


def last_game(row: LeagueCatalog) -> int | None:
    """Its last game, else the end date Liquipedia gives it."""
    return row.last_game or day_end(row.end_date)


def status(row: LeagueCatalog, now: float) -> str:
    if row.live_seen and now - row.live_seen <= LIVE_MINUTES * 60:
        return "live"
    last = last_game(row)
    if last is None:
        return "unknown"
    return "active" if now - last <= ACTIVE_DAYS * 86400 else "finished"


def row(r: LeagueCatalog, now: float, subscribed: set[int]) -> dict:
    """A catalog row as the site gets it."""
    columns = {c.name: getattr(r, c.name) for c in LeagueCatalog.__table__.columns if c.name != "refreshed"}
    return {**columns, "last": last_game(r), "status": status(r, now), "subscribed": r.league_id in subscribed}


def search(
    session: Session, text: str = "", tier: str = "", state: str = "", sort: str = "last", offset: int = 0,
    limit: int = 50, now: float | None = None,
) -> list[dict]:  # fmt: skip
    """Leagues whose name holds `text` (any case, literally), of a tier (premium, professional, amateur: amateur,
    excluded or none) and a `state` (status: live, active, finished, unknown), in the order `sort` names (SORTS)."""
    now = now or time.time()
    query = select(LeagueCatalog).order_by(LeagueCatalog.league_id.desc())
    if text.strip():
        escaped = text.strip().replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_")
        query = query.where(LeagueCatalog.name.ilike(f"%{escaped}%", escape="\\"))
    if tier == "amateur":
        query = query.where(or_(LeagueCatalog.tier.in_(("amateur", "excluded")), LeagueCatalog.tier.is_(None)))
    elif tier:
        query = query.where(LeagueCatalog.tier == tier)
    subscribed = set(session.scalars(select(League.league_id)))
    rows = [row(r, now, subscribed) for r in session.scalars(query)]
    if state:
        rows = [r for r in rows if r["status"] == state]
    rows.sort(key=SORTS.get(sort, SORTS["last"]))  # stable: the newest first among equals
    return rows[offset : offset + limit]


def explore(session: Session, now: float | None = None) -> dict:
    """Explore: the leagues live now, most live games first, and the BIG biggest of the last ACTIVE_DAYS days,
    by Liquipedia tier (1 first, none last), then prize pool, then games."""
    now = now or time.time()
    recent = select(LeagueCatalog).where(or_(
        LeagueCatalog.last_game >= now - ACTIVE_DAYS * 86400, LeagueCatalog.live_seen >= now - LIVE_MINUTES * 60,
        LeagueCatalog.end_date.is_not(None),  # an end date is checked in Python
    )).order_by(LeagueCatalog.league_id.desc())  # fmt: skip
    subscribed = set(session.scalars(select(League.league_id)))
    rows = [r for r in (row(x, now, subscribed) for x in session.scalars(recent)) if r["status"] in ("live", "active")]
    live = sorted((r for r in rows if r["status"] == "live"), key=lambda r: -r["live_games"])
    big = sorted(rows, key=lambda r: (r["lp_tier"] or 99, -(r["prize_usd"] or 0), -(r["games"] or 0)))
    return {"live": live, "big": big[:BIG]}
