import asyncio
import logging
import os
import time
from pathlib import Path

import httpx
from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from .db import DATA, Match
from .replay import ReplayError, fetch_replay, parse_replay
from .steam import sync

log = logging.getLogger("uvicorn.error")  # the logger uvicorn already prints
REPLAY_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\replays")
SETTLE_SECONDS = 120
RETRY_SECONDS = 3600
MAX_AGE_DAYS = 30  # how far back replays are downloaded; Valve keeps them about 100 days
DOWNLOADS_PER_POLL = 10  # about 40 MB each; also keeps OpenDota calls far below its 60 a minute


def poll_once(
    session: Session, client: httpx.Client, key: str, replay_dir: Path, data: Path = DATA
) -> tuple[int, int]:
    """Sync all accounts, parse replays the Dota client has downloaded, then download missing ones.

    Returns (new matches, replays parsed).
    """
    new = 0
    if key:
        new = sum(count or 0 for count in sync(session, client, key).values())
    else:
        log.warning("STEAM_API_KEY is not set, skipping sync")

    parsed = 0
    for dem in sorted(replay_dir.glob("*.dem")) if replay_dir.is_dir() else []:
        if not dem.stem.isdigit():
            continue
        match = session.get(Match, int(dem.stem))
        if match is None or match.replay_state in ("parsed", "failed"):
            continue
        # a file the Dota client is still writing would parse as truncated and be marked failed for good
        if time.time() - dem.stat().st_mtime < SETTLE_SECONDS:
            continue
        try:
            parse_replay(session, dem, client, data / "raw")
            parsed += 1
        except (ReplayError, OSError, httpx.HTTPError) as error:
            log.warning("replay %s: %s", dem.name, error)

    # never tried first, so a new match is not stuck behind retries; each group newest first
    now = time.time()
    due = (
        select(Match)
        .where(
            # a match already tried is followed up whatever its age, so it cannot stay pending for ever
            or_(
                Match.replay_state == "pending",
                and_(Match.replay_state == "none", Match.start_time > now - MAX_AGE_DAYS * 86400),
            ),
            or_(Match.replay_tried_at.is_(None), Match.replay_tried_at < now - RETRY_SECONDS),
        )
        .order_by(Match.replay_tried_at.is_not(None), Match.start_time.desc())
        .limit(DOWNLOADS_PER_POLL)
    )
    for match in session.scalars(due).all():
        try:
            parsed += fetch_replay(session, match, client, data)
        except ReplayError as error:
            log.warning("replay download: %s", error)
        except (OSError, httpx.HTTPError) as error:
            # a server or the disk is in trouble: leave the rest for the next poll
            log.warning("replay download of match %s stopped: %r", match.match_id, error)
            break
    return new, parsed


def _run(engine: Engine) -> tuple[int, int]:
    replay_dir = Path(os.environ.get("DOTA_REPLAY_DIR", REPLAY_DIR))
    with Session(engine) as session, httpx.Client() as client:
        return poll_once(session, client, os.environ.get("STEAM_API_KEY", ""), replay_dir)


async def poll_forever(engine: Engine) -> None:
    minutes = float(os.environ.get("POLL_MINUTES", 15))
    while True:
        try:
            new, parsed = await asyncio.to_thread(_run, engine)
            log.info("poll: %s new matches, %s replays parsed, next in %g min", new, parsed, minutes)
        except Exception:  # one bad poll must not end polling
            log.exception("poll failed, next in %g min", minutes)
        await asyncio.sleep(minutes * 60)
