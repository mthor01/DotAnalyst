import asyncio
import logging
import os
import threading
import time
from pathlib import Path

import httpx
from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.orm import Session

from .db import DATA, Match, PlayerMinute
from .derive import derive_match
from .replay import ReplayError, fetch_replay, parse_replay, steam_salts
from .steam import sync, sync_leagues

log = logging.getLogger("uvicorn.error")  # the logger uvicorn already prints
REPLAY_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\replays")
SETTLE_SECONDS = 120
RETRY_SECONDS = 3600
MAX_AGE_DAYS = 30  # how far back replays are downloaded; Valve keeps them about 100 days
DOWNLOADS_PER_POLL = 10  # about 40 MB each; also keeps OpenDota calls far below its 60 a minute
BUSY = threading.Lock()  # the timed poll and a refresh from the site never fetch at the same time


def poll_once(
    session: Session, client: httpx.Client, key: str, replay_dir: Path, data: Path = DATA, alt: bool = False,
    retry_seconds: int = RETRY_SECONDS,
) -> tuple[int, int]:  # fmt: skip
    """Sync all accounts, parse replays the Dota client has downloaded, download missing ones,
    then compute the stats of every parsed match that has none.

    A replay that was not there is tried again after retry_seconds. Returns (new matches, replays parsed).
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
            or_(Match.replay_tried_at.is_(None), Match.replay_tried_at < now - retry_seconds),
        )
        .order_by(Match.replay_tried_at.is_not(None), Match.start_time.desc())
        .limit(DOWNLOADS_PER_POLL)
    )
    matches = session.scalars(due).all()
    salts = {}
    if alt and matches:  # the second Steam account asks Valve; OpenDota is asked for what that leaves open
        try:
            salts = steam_salts([match.match_id for match in matches], data)
        except ReplayError as error:
            log.warning("replay salts from Steam: %s; asking OpenDota instead", error)
    for match in matches:
        try:
            parsed += fetch_replay(session, match, client, data, salts.get(match.match_id))
        except ReplayError as error:
            log.warning("replay download: %s", error)
        except (OSError, httpx.HTTPError) as error:
            # a server or the disk is in trouble: leave the rest for the next poll
            log.warning("replay download of match %s stopped: %r", match.match_id, error)
            break

    without_stats = select(Match.match_id).where(
        Match.replay_state == "parsed", Match.match_id.not_in(select(PlayerMinute.match_id))
    )
    for match_id in session.scalars(without_stats).all():
        try:
            derive_match(session, match_id, data / "raw")
        except Exception:  # a log one derivation cannot handle must not stop polling
            session.rollback()
            log.exception("replay stats of match %s failed", match_id)
    return new, parsed


def request_replay(
    session: Session, client: httpx.Client, match_id: int, data: Path = DATA, alt: bool = False
) -> str | None:
    """Download and parse one match's replay now, whatever its age and whenever it was last tried, and compute its
    stats. Returns the match's replay state afterwards, or None for a match that is not stored."""
    match = session.get(Match, match_id)
    if match is None:
        return None
    if match.replay_state != "parsed":  # a stored replay is never fetched again
        salt = None
        if alt:
            try:
                salt = steam_salts([match_id], data).get(match_id)
            except ReplayError as error:
                log.warning("replay salt from Steam: %s; asking OpenDota instead", error)
        if fetch_replay(session, match, client, data, salt):
            derive_match(session, match_id, data / "raw")
    return match.replay_state


def refresh_replay(engine: Engine, match_id: int) -> str | None:
    """`request_replay`, asked for from the site. Whatever stops it is a ReplayError."""
    with BUSY, Session(engine) as session, httpx.Client() as client:
        try:
            return request_replay(session, client, match_id, alt=bool(os.environ.get("STEAM_ALT_USER")))
        except (OSError, httpx.HTTPError) as error:
            raise ReplayError(f"the download or the parser failed ({type(error).__name__}); is Docker running?") from error


def _run(engine: Engine, retry_seconds: int = RETRY_SECONDS) -> tuple[int, int]:
    replay_dir = Path(os.environ.get("DOTA_REPLAY_DIR", REPLAY_DIR))
    with BUSY, Session(engine) as session, httpx.Client() as client:
        return poll_once(
            session, client, os.environ.get("STEAM_API_KEY", ""), replay_dir,
            alt=bool(os.environ.get("STEAM_ALT_USER")), retry_seconds=retry_seconds,
        )  # fmt: skip


def refresh(engine: Engine) -> dict:
    """A poll asked for from the site. It tries every waiting replay again, whenever it was last tried."""
    new, parsed = _run(engine, retry_seconds=0)
    with Session(engine) as session:
        waiting = session.scalar(select(func.count()).select_from(Match).where(Match.replay_state == "pending"))
    return {"matches": new, "replays": parsed, "waiting": waiting}


def refresh_leagues(engine: Engine) -> dict:
    """New league games, asked for from the site."""
    with BUSY, Session(engine) as session, httpx.Client() as client:
        return {"league_games": sync_leagues(session, client, os.environ.get("STEAM_API_KEY", ""))}


async def poll_forever(engine: Engine) -> None:
    minutes = float(os.environ.get("POLL_MINUTES", 15))
    while True:
        try:
            new, parsed = await asyncio.to_thread(_run, engine)
            log.info("poll: %s new matches, %s replays parsed, next in %g min", new, parsed, minutes)
        except Exception:  # one bad poll must not end polling
            log.exception("poll failed, next in %g min", minutes)
        await asyncio.sleep(minutes * 60)
