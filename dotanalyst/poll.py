import asyncio
import logging
import os
import time
from pathlib import Path

import httpx
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from .db import DATA, Match
from .replay import ReplayError, parse_replay
from .steam import sync

log = logging.getLogger("uvicorn.error")  # the logger uvicorn already prints
REPLAY_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\replays")
SETTLE_SECONDS = 120


def poll_once(
    session: Session, client: httpx.Client, key: str, replay_dir: Path, raw_dir: Path = DATA / "raw"
) -> tuple[int, int]:
    """Sync all accounts, then parse replays the Dota client has downloaded. Returns (new matches, replays parsed)."""
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
            parse_replay(session, dem, client, raw_dir)
            parsed += 1
        except (ReplayError, OSError, httpx.HTTPError) as error:
            log.warning("replay %s: %s", dem.name, error)
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
