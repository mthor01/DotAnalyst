"""The tournament browser's list of every league (league_catalog): OpenDota's league list and the dates of the pro
leagues once a day, the leagues playing right now from Steam's live list, and the search and Explore page over it.
See Tournament browser in IMPLEMENTATION.md."""
import logging
import time

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import LeagueCatalog
from .opendota import pace

LEAGUES = "https://api.opendota.com/api/leagues"
EXPLORER = "https://api.opendota.com/api/explorer"
STALE = 86400  # OpenDota's list is read again after a day
ACTIVITY_DAYS = 365  # the explorer counts the pro games of this many days back
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
