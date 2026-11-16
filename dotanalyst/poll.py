import asyncio
import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path

import httpx
from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.orm import Session

from .db import DATA, LeagueMatch, Match, PlayerMinute
from .derive import derive_match
from .opendota import fetch_player_games, unlisted_players
from .replay import PARSER_URL, ReplayError, fetch_replay, parse_replay, replay_complete, steam_salts
from .steam import store_match, sync, sync_leagues

log = logging.getLogger("uvicorn.error")  # the logger uvicorn already prints
REPLAY_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\replays")
RETRY_SECONDS = 3600
MAX_AGE_DAYS = 30  # how far back replays are downloaded; Valve keeps them about 100 days
DOWNLOADS_PER_POLL = 10  # about 40 MB each; also keeps OpenDota calls far below its 60 a minute
PLAYERS_PER_POLL = 5  # league players whose own games are asked of OpenDota, one call each
BUSY = threading.Lock()  # the timed poll and a refresh from the site never fetch at the same time
# for the queue page; kept in memory only, so a restart starts them empty
NOW = {"doing": "starting", "since": time.time(), "last_poll": None, "next_poll": None}
EVENTS: deque[dict] = deque(maxlen=200)


def doing(what: str) -> None:
    NOW.update(doing=what, since=time.time())


def event(match_id: int | None, message: str, warn: bool = True) -> None:
    if warn:
        log.warning("match %s: %s", match_id, message)
    EVENTS.append({"at": time.time(), "match_id": match_id, "message": message})


def wanted(now: float):
    """Matches whose replay the poller still wants, whenever it next tries them."""
    return or_(
        Match.replay_state == "pending",
        and_(Match.replay_state == "none", Match.start_time > now - MAX_AGE_DAYS * 86400),
    )


def folder_replays(session: Session, replay_dir: Path) -> list[Path]:
    """The .dem files in the Dota client folder of stored matches that have no parse yet."""
    found = []
    for dem in sorted(replay_dir.glob("*.dem")) if replay_dir.is_dir() else []:
        match = session.get(Match, int(dem.stem)) if dem.stem.isdigit() else None
        if match is not None and match.replay_state not in ("parsed", "failed"):
            found.append(dem)
    return found


def poll_once(
    session: Session, client: httpx.Client, key: str, replay_dir: Path, data: Path = DATA, alt: bool = False,
    retry_seconds: int = RETRY_SECONDS, newest_only: bool = False,
) -> tuple[int, int]:  # fmt: skip
    """Sync all accounts and the leagues, parse replays the Dota client has downloaded, download missing ones of
    account matches and of league games, then compute the stats of every parsed match that has none.

    A replay that was not there is tried again after retry_seconds. newest_only reads Steam's lists only until a page
    that is all stored. Returns (new matches, replays parsed).
    """
    new = 0
    if key:
        doing("asking Steam for new matches of the accounts")
        new = sum(count or 0 for count in sync(session, client, key, newest_only).values())
        doing("asking Steam for new league games")
        new += sync_leagues(session, client, key, newest_only)
    else:
        log.warning("STEAM_API_KEY is not set, skipping sync")

    # a league game young enough to download becomes a match like any other: its replay is fetched and its stats
    # computed below. No tracked account plays in it, so it joins nobody's stats
    recent = select(LeagueMatch.raw_json).where(
        LeagueMatch.start_time > time.time() - MAX_AGE_DAYS * 86400, LeagueMatch.match_id.not_in(select(Match.match_id))
    )
    for raw in session.scalars(recent).all():
        store_match(session, raw)
    session.commit()

    parsed = 0
    for dem in folder_replays(session, replay_dir):
        # a file the Dota client is still writing would parse as truncated and be marked failed for good
        if not replay_complete(dem):
            continue
        doing(f"parsing {dem.name} from the Dota client folder")
        try:
            parse_replay(session, dem, client, data / "raw")
            parsed += 1
            event(int(dem.stem), "parsed from the Dota client folder", warn=False)
        except (ReplayError, OSError, httpx.HTTPError) as error:
            event(int(dem.stem), f"{dem.name} from the Dota client folder: {error!r}")

    # never tried first, so a new match is not stuck behind retries; each group newest first
    now = time.time()
    due = (
        select(Match)
        # a match already tried is followed up whatever its age, so it cannot stay pending for ever
        .where(wanted(now), or_(Match.replay_tried_at.is_(None), Match.replay_tried_at < now - retry_seconds))
        .order_by(Match.replay_tried_at.is_not(None), Match.start_time.desc())
        .limit(DOWNLOADS_PER_POLL)
    )
    matches = session.scalars(due).all()
    salts = {}
    if alt and matches:  # the second Steam account asks Valve; OpenDota is asked for what that leaves open
        doing(f"asking Valve for {len(matches)} replay salts with the second Steam account")
        try:
            salts = steam_salts([match.match_id for match in matches], data)
        except ReplayError as error:
            event(None, f"replay salts from Steam: {error}; asking OpenDota instead")
    for i, match in enumerate(matches, 1):
        doing(f"downloading and parsing match {match.match_id} ({i} of {len(matches)})")
        try:
            if fetch_replay(session, match, client, data, salts.get(match.match_id)):
                parsed += 1
                event(match.match_id, "downloaded and parsed", warn=False)
            else:
                salted = match.match_id in salts or (data / "opendota" / f"{match.match_id}.json.gz").exists()
                why = "Valve has no file for it" if salted else "no salt: OpenDota does not know it"
                event(match.match_id, f"no replay yet ({why}), now {match.replay_state}", warn=False)
        except ReplayError as error:
            event(match.match_id, str(error))
        except (OSError, httpx.HTTPError) as error:
            # a server or the disk is in trouble: leave the rest for the next poll
            event(match.match_id, f"download stopped, the rest waits for the next poll: {error!r}")
            break

    # the league players' own games, for their role wheel on the team page: the list only, never a replay
    players = unlisted_players(session, PLAYERS_PER_POLL)
    for i, account_id in enumerate(players, 1):
        doing(f"asking OpenDota for the last games of player {account_id} ({i} of {len(players)})")
        try:
            fetch_player_games(session, client, account_id)
        except httpx.HTTPError as error:
            session.rollback()
            event(None, f"games of player {account_id}, the rest waits for the next poll: {error!r}")
            break

    without_stats = select(Match.match_id).where(
        Match.replay_state == "parsed", Match.match_id.not_in(select(PlayerMinute.match_id))
    )
    for match_id in session.scalars(without_stats).all():
        doing(f"computing the stats of match {match_id}")
        try:
            derive_match(session, match_id, data / "raw")
        except Exception as error:  # a log one derivation cannot handle must not stop polling
            session.rollback()
            log.exception("replay stats of match %s failed", match_id)
            event(match_id, f"stats failed: {error!r}", warn=False)
    return new, parsed


def queue(session: Session, replay_dir: Path, data: Path = DATA, now: float | None = None) -> dict:
    """What the poller has to do, for the queue page: every match whose replay it still wants, in the order it will
    take them, and what it is doing and did lately."""
    now = now or time.time()
    waiting = session.scalars(select(Match).where(wanted(now))).all()
    league = set(session.scalars(select(LeagueMatch.match_id).where(LeagueMatch.match_id.in_(m.match_id for m in waiting))))
    last = {e["match_id"]: e for e in EVENTS}

    def next_try(m: Match) -> float:
        return now if m.replay_tried_at is None else max(now, m.replay_tried_at + RETRY_SECONDS)

    # due first, in the poller's order (never tried, then newest); the rest by when they are due
    waiting = sorted(waiting, key=lambda m: (next_try(m), m.replay_tried_at is not None, -m.start_time))
    states = dict(session.execute(select(Match.replay_state, func.count()).group_by(Match.replay_state)).all())
    without_stats = select(func.count()).select_from(Match).where(
        Match.replay_state == "parsed", Match.match_id.not_in(select(PlayerMinute.match_id))
    )
    in_folder = folder_replays(session, replay_dir)
    ready = sum(map(replay_complete, in_folder))
    salts = data / "salts.json"
    try:
        httpx.get(PARSER_URL, timeout=1)  # any answer will do: it shows the container is up
        parser = True
    except httpx.HTTPError:
        parser = False
    return {
        **NOW, "busy": BUSY.locked(), "now": now, "parser": parser, "alt": bool(os.environ.get("STEAM_ALT_USER")),
        "salts_from_steam": len(json.loads(salts.read_text())) if salts.exists() else 0,
        "per_poll": DOWNLOADS_PER_POLL, "retry_seconds": RETRY_SECONDS, "max_age_days": MAX_AGE_DAYS,
        "states": states, "without_stats": session.scalar(without_stats),
        "folder": {"ready": ready, "downloading": len(in_folder) - ready},
        "queue": [
            {
                "match_id": m.match_id, "start_time": m.start_time, "league": m.match_id in league,
                "state": m.replay_state, "tried_at": m.replay_tried_at, "next_try": next_try(m),
                "last": last.get(m.match_id),
            }
            for m in waiting
        ],
        "events": list(reversed(EVENTS))[:100],
    }  # fmt: skip


def request_replay(
    session: Session, client: httpx.Client, match_id: int, data: Path = DATA, alt: bool = False
) -> str | None:
    """Download and parse one match's replay now, whatever its age and whenever it was last tried, and compute its
    stats. Returns the match's replay state afterwards, or None for a match that is not stored.

    A league game joins `matches` here, built from the answer Steam gave for it: from then on it is a match like any
    other, with a replay state the poller follows up. No tracked account plays in it, so it joins nobody's stats.
    """
    match = session.get(Match, match_id)
    if match is None:
        league = session.get(LeagueMatch, match_id)
        if league is None:
            return None
        store_match(session, league.raw_json)
        session.flush()
        match = session.get(Match, match_id)
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
            reason = f"the download or the parser failed ({type(error).__name__}); is Docker running?"
            raise ReplayError(reason) from error


def _run(engine: Engine, retry_seconds: int = RETRY_SECONDS, newest_only: bool = True) -> tuple[int, int]:
    with BUSY, Session(engine) as session, httpx.Client() as client:
        start = time.time()
        try:
            new, parsed = poll_once(
                session, client, os.environ.get("STEAM_API_KEY", ""), replay_dir(),
                alt=bool(os.environ.get("STEAM_ALT_USER")), retry_seconds=retry_seconds, newest_only=newest_only,
            )  # fmt: skip
            NOW["last_poll"] = {"at": start, "seconds": time.time() - start, "new": new, "parsed": parsed}
            return new, parsed
        except Exception as error:
            NOW["last_poll"] = {"at": start, "seconds": time.time() - start, "error": repr(error)}
            raise
        finally:
            doing("waiting for the next poll")


def replay_dir() -> Path:
    return Path(os.environ.get("DOTA_REPLAY_DIR", REPLAY_DIR))


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
    minutes = float(os.environ.get("POLL_MINUTES", 1))
    newest_only = False  # the first poll reads Steam's whole lists, to pick up what an interrupted run left out
    while True:
        try:
            new, parsed = await asyncio.to_thread(_run, engine, RETRY_SECONDS, newest_only)
            newest_only = True
            log.info("poll: %s new matches, %s replays parsed, next in %g min", new, parsed, minutes)
        except Exception:  # one bad poll must not end polling
            log.exception("poll failed, next in %g min", minutes)
        NOW["next_poll"] = time.time() + minutes * 60
        await asyncio.sleep(minutes * 60)
