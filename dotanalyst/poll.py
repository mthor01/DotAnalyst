import asyncio
import logging
import math
import os
import threading
import time
from collections import deque
from pathlib import Path

import httpx
from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.orm import Session

from .db import (
    DATA, Account, League, LeagueMatch, Match, MatchPlayer, PlayerGame, PlayerGameList, PlayerMinute, PlayerName,
)  # fmt: skip
from .derive import derive_match
from .opendota import fetch_player_games, unlisted_players, usual_match
from .replay import (
    MAX_AGE_DAYS, PARSER_URL, ReplayError, fetch_replay, opendota_match, parse_replay, replay_complete, steam_salts,
)  # fmt: skip
from .steam import store_match, sync, sync_leagues

log = logging.getLogger("uvicorn.error")  # the logger uvicorn already prints
REPLAY_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\replays")
RETRY_SECONDS = 3600
DOWNLOADS_PER_POLL = 10  # about 40 MB each; also keeps OpenDota calls far below its 60 a minute
PLAYERS_PER_POLL = 5  # league players whose own games are asked of OpenDota, one call each
USUAL_PER_POLL = 10  # usual games of a checked team's players turned into matches, one OpenDota call each
# shortcut: forgotten on restart, so OpenDota is asked once more per run for a game it cannot give; store it if that adds up
NO_MATCH: set[int] = set()
BUSY = threading.Lock()  # the timed poll and a refresh from the site never fetch at the same time
# for the queue page; kept in memory only, so a restart starts them empty
NOW = {"doing": "starting", "step": None, "since": time.time(), "last_poll": None, "next_poll": None}
EVENTS: deque[dict] = deque(maxlen=200)
STEPS: dict[str, dict] = {}  # per step of poll_once: when it last ended and what it did
# what takes room in the data folder, in the order the storage chart colours it; everything else is "Other"
STORAGE = {"raw": "Parser output", "dotanalyst.db": "Database", "opendota": "OpenDota answers",
           "steam": "Steam answers", "tmp": "Replays being fetched"}  # fmt: skip


def doing(what: str, step: str | None = None) -> None:
    NOW.update(doing=what, step=step, since=time.time())


def did(step: str, what: str) -> None:
    STEPS[step] = {"at": time.time(), "what": what}


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


def usual_waiting(now: float):
    """Usual games of a checked team's players young enough to become matches and not yet stored, newest first."""
    return (
        select(PlayerGame.match_id).distinct()
        .join(PlayerGameList, and_(PlayerGameList.account_id == PlayerGame.account_id, PlayerGameList.replays_wanted))
        .where(PlayerGame.start_time > now - MAX_AGE_DAYS * 86400, PlayerGame.match_id.not_in(select(Match.match_id)))
        .where(PlayerGame.match_id.not_in(NO_MATCH))
        .order_by(PlayerGame.match_id.desc())
    )  # fmt: skip


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
    new = league_new = 0
    if key:
        doing("asking Steam for new matches of the accounts", "accounts")
        new = sum(count or 0 for count in sync(session, client, key, newest_only).values())
        did("accounts", f"{new} new matches")
        doing("asking Steam for new league games", "leagues")
        league_new = sync_leagues(session, client, key, newest_only)
        new += league_new
    else:
        log.warning("STEAM_API_KEY is not set, skipping sync")

    # a league game young enough to download becomes a match like any other: its replay is fetched and its stats
    # computed below. No tracked account plays in it, so it joins nobody's stats
    recent = select(LeagueMatch.raw_json).where(
        LeagueMatch.start_time > time.time() - MAX_AGE_DAYS * 86400, LeagueMatch.match_id.not_in(select(Match.match_id))
    )
    young = session.scalars(recent).all()
    for raw in young:
        store_match(session, raw)
    session.commit()
    if key:
        did("leagues", f"{league_new} new league games, {len(young)} young enough joined the replay queue")

    # the usual games of a checked team's players become matches too, from OpenDota's answer, which also holds the
    # salt the download below needs; they join nobody's stats either, only the players' ward maps
    usual = session.scalars(usual_waiting(time.time()).limit(USUAL_PER_POLL)).all()
    stored, stopped = 0, ""
    for match_id in usual:
        doing(f"asking OpenDota for usual match {match_id} of a checked team's player", "usual")
        try:
            found = usual_match(opendota_match(match_id, client, data / "opendota"), match_id)
        except httpx.HTTPError as error:
            event(match_id, f"usual match from OpenDota, the rest waits for the next poll: {error!r}")
            stopped = f"; then OpenDota failed: {error!r}"
            break
        if found is None:
            NO_MATCH.add(match_id)
            event(match_id, "OpenDota does not know this usual match", warn=False)
            continue
        store_match(session, found)
        session.commit()
        stored += 1
    did("usual", f"{stored} of {len(usual)} became matches{stopped}")

    parsed = 0
    in_folder = folder_replays(session, replay_dir)
    for dem in in_folder:
        # a file the Dota client is still writing would parse as truncated and be marked failed for good
        if not replay_complete(dem):
            continue
        doing(f"parsing {dem.name} from the Dota client folder", "folder")
        try:
            parse_replay(session, dem, client, data / "raw")
            parsed += 1
            event(int(dem.stem), "parsed from the Dota client folder", warn=False)
        except (ReplayError, OSError, httpx.HTTPError) as error:
            event(int(dem.stem), f"{dem.name} from the Dota client folder: {error!r}")
    did("folder", f"{parsed} of {len(in_folder)} parsed")

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
        doing(f"asking Valve for {len(matches)} replay salts with the second Steam account", "salts")
        try:
            salts = steam_salts([match.match_id for match in matches], data)
            did("salts", f"{len(salts)} of {len(matches)} salts from Valve")
        except ReplayError as error:
            event(None, f"replay salts from Steam: {error}; asking OpenDota instead")
            did("salts", f"Steam failed, OpenDota asked instead: {error}")
    downloaded, stopped = 0, ""
    for i, match in enumerate(matches, 1):
        doing(f"downloading and parsing match {match.match_id} ({i} of {len(matches)})", "downloads")
        try:
            if fetch_replay(session, match, client, data, salts.get(match.match_id)):
                parsed += 1
                downloaded += 1
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
            stopped = f"; then stopped: {error!r}"
            break
    did("downloads", f"{downloaded} of {len(matches)} downloaded and parsed{stopped}")

    # the league players' own games, for their role wheel on the team page: the list only, never a replay
    players = unlisted_players(session, PLAYERS_PER_POLL)
    listed, stopped = 0, ""
    for i, account_id in enumerate(players, 1):
        doing(f"asking OpenDota for the last games of player {account_id} ({i} of {len(players)})", "players")
        try:
            fetch_player_games(session, client, account_id)
            listed += 1
        except httpx.HTTPError as error:
            session.rollback()
            event(None, f"games of player {account_id}, the rest waits for the next poll: {error!r}")
            stopped = f"; then OpenDota failed: {error!r}"
            break
    did("players", f"{listed} of {len(players)} players' game lists fetched{stopped}")

    to_derive = session.scalars(without_stats()).all()
    failed = 0
    for match_id in to_derive:
        doing(f"computing the stats of match {match_id}", "stats")
        try:
            derive_match(session, match_id, data / "raw")
        except Exception as error:  # a log one derivation cannot handle must not stop polling
            session.rollback()
            log.exception("replay stats of match %s failed", match_id)
            event(match_id, f"stats failed: {error!r}", warn=False)
            failed += 1
    did("stats", f"{len(to_derive) - failed} of {len(to_derive)} computed")
    return new, parsed


def without_stats():
    """Parsed matches whose stats are not computed yet."""
    return select(Match.match_id).where(
        Match.replay_state == "parsed", Match.match_id.not_in(select(PlayerMinute.match_id))
    )


def storage(data: Path) -> list[dict]:
    """Bytes in the data folder by what holds them, in STORAGE's order and then Other; parts that hold none too."""
    sizes = dict.fromkeys([*STORAGE.values(), "Other"], 0)
    for path in data.rglob("*") if data.is_dir() else []:
        try:
            size = path.stat().st_size if path.is_file() else 0
        except OSError:  # a replay deleted while we walk
            continue
        top = path.relative_to(data).parts[0]
        part = STORAGE.get(top) or STORAGE.get(top.split("-")[0]) or "Other"  # dotanalyst.db-wal is the database too
        sizes[part] += size
    return [{"name": name, "bytes": size} for name, size in sizes.items()]


def whose(session: Session, ids: list[int]) -> dict[int, dict]:
    """Per match: the tracked accounts that played it, the checked players it is a usual game of, its league."""
    found = {i: {"accounts": [], "usual": [], "league": None} for i in ids}
    accounts = (
        select(MatchPlayer.match_id, Account.account_id, Account.label, Account.avatar)
        .join(Account, Account.account_id == MatchPlayer.account_id).where(MatchPlayer.match_id.in_(ids))
    )  # fmt: skip
    for match_id, account_id, name, avatar in session.execute(accounts):
        found[match_id]["accounts"].append({"account_id": account_id, "name": name, "avatar": avatar or None})
    usual = (
        select(PlayerGame.match_id, PlayerGame.account_id, PlayerName.name, PlayerName.avatar)
        .join(PlayerGameList, and_(PlayerGameList.account_id == PlayerGame.account_id, PlayerGameList.replays_wanted))
        .outerjoin(PlayerName, PlayerName.account_id == PlayerGame.account_id).where(PlayerGame.match_id.in_(ids))
    )  # fmt: skip
    for match_id, account_id, name, avatar in session.execute(usual):
        found[match_id]["usual"].append({"account_id": account_id, "name": name, "avatar": avatar or None})
    leagues = (
        select(LeagueMatch.match_id, LeagueMatch.league_id, League.name)
        .outerjoin(League, League.league_id == LeagueMatch.league_id).where(LeagueMatch.match_id.in_(ids))
    )  # fmt: skip
    for match_id, league_id, name in session.execute(leagues):
        found[match_id]["league"] = name or f"League {league_id}"
    return found


def queue(session: Session, replay_dir: Path, data: Path = DATA, now: float | None = None) -> dict:
    """What the poller has to do, for the queue page: every match whose replay it still wants, in the order it will
    take them, and what it is doing and did lately."""
    now = now or time.time()
    waiting = session.scalars(select(Match).where(wanted(now))).all()
    last = {e["match_id"]: e for e in EVENTS}

    def next_try(m: Match) -> float:
        return now if m.replay_tried_at is None else max(now, m.replay_tried_at + RETRY_SECONDS)

    # due first, in the poller's order (never tried, then newest); the rest by when they are due
    waiting = sorted(waiting, key=lambda m: (next_try(m), m.replay_tried_at is not None, -m.start_time))
    states = dict(session.execute(select(Match.replay_state, func.count()).group_by(Match.replay_state)).all())
    try:
        httpx.get(PARSER_URL, timeout=1)  # any answer will do: it shows the container is up
        parser = True
    except httpx.HTTPError:
        parser = False
    names = whose(session, [m.match_id for m in waiting])
    return {
        **NOW, "busy": BUSY.locked(), "now": now, "parser": parser,
        "per_poll": DOWNLOADS_PER_POLL, "retry_seconds": RETRY_SECONDS, "max_age_days": MAX_AGE_DAYS,
        "states": states, "steps": steps(session, replay_dir, waiting, next_try, parser, now),
        "storage": storage(data),
        "queue": [
            {
                "match_id": m.match_id, "start_time": m.start_time, **names[m.match_id],
                "state": m.replay_state, "tried_at": m.replay_tried_at, "next_try": next_try(m),
                "last": last.get(m.match_id),
            }
            for m in waiting
        ],
        "events": list(reversed(EVENTS))[:100],
    }  # fmt: skip


def steps(session: Session, replay_dir: Path, waiting: list[Match], next_try, parser: bool, now: float) -> list[dict]:
    """Each step of a poll in its order: what it did last, what the next poll will do in it, and why some of what
    waits is not done then."""
    key, alt = os.environ.get("STEAM_API_KEY"), os.environ.get("STEAM_ALT_USER")
    no_key = None if key else "STEAM_API_KEY is not set in .env, so Steam is not asked"
    no_parser = None if parser else "the parser does not answer on port 5600: is its Docker container running?"
    accounts = session.scalar(select(func.count()).select_from(Account).where(Account.active))
    leagues = session.scalar(select(func.count()).select_from(League))
    usual = session.scalar(select(func.count()).select_from(usual_waiting(now).subquery()))
    in_folder = folder_replays(session, replay_dir)
    ready = sum(map(replay_complete, in_folder))
    due = [m for m in waiting if next_try(m) <= now]
    later = [next_try(m) for m in waiting if next_try(m) > now]
    old = session.scalar(
        select(func.count()).select_from(Match)
        .where(Match.replay_state == "none", Match.start_time <= now - MAX_AGE_DAYS * 86400)
    )  # fmt: skip
    # shortcut: walks every league game (about 0.2 s on 2000 games) on each refresh of the page; cache it if that grows
    players = len(unlisted_players(session, 10**9))
    derive = session.scalar(select(func.count()).select_from(without_stats().subquery()))

    def why(*reasons):
        return [r for r in reasons if r]

    return [{**step, "last": STEPS.get(step["key"])} for step in [
        {"key": "accounts", "name": "New matches of the accounts",
         "planned": f"Steam's newest matches of the {accounts} tracked accounts", "why": why(no_key)},
        {"key": "leagues", "name": "New league games",
         "planned": f"Steam's newest games of the {leagues} tracked tournaments; those of the last {MAX_AGE_DAYS} "
                    "days join the replay queue", "why": why(no_key)},
        {"key": "usual", "name": "Usual games of checked players",
         "planned": f"{min(usual, USUAL_PER_POLL)} of {usual} waiting games asked of OpenDota, to become matches",
         "why": why(
             usual > USUAL_PER_POLL and f"{usual - USUAL_PER_POLL} wait for later polls: {USUAL_PER_POLL} a poll, "
                                       "one OpenDota call each",
             NO_MATCH and f"{len(NO_MATCH)} OpenDota does not know are skipped until the server restarts",
         )},
        {"key": "folder", "name": "Replays in the Dota client folder",
         "planned": f"{ready} replays the Dota client downloaded to parse",
         "why": why(
             len(in_folder) > ready and f"{len(in_folder) - ready} are still being written by the Dota client",
             ready and no_parser,
         )},
        {"key": "salts", "name": "Replay ids from Valve",
         "planned": f"the replay ids (salts) of the {min(len(due), DOWNLOADS_PER_POLL)} next downloads" if alt
                    else "none: OpenDota gives the replay ids (salts)",
         "why": why(not alt and "STEAM_ALT_USER is not set in .env, so the second Steam account does not ask Valve")},
        {"key": "downloads", "name": "Replay downloads and parsing",
         "planned": f"{min(len(due), DOWNLOADS_PER_POLL)} of {len(due)} due replays downloaded and parsed",
         "why": why(
             len(due) > DOWNLOADS_PER_POLL and f"{len(due) - DOWNLOADS_PER_POLL} due wait for later polls: "
                                               f"{DOWNLOADS_PER_POLL} a poll, about 40 MB each",
             later and f"{len(later)} tried within the last {RETRY_SECONDS // 60} minutes wait for their retry, the "
                       f"next in {math.ceil((min(later) - now) / 60)} min",
             due and no_parser,
             old and f"{old} without a replay older than {MAX_AGE_DAYS} days are left alone; Request replay on the "
                     "match page fetches one",
         )},
        {"key": "players", "name": "Game lists of league players",
         "planned": f"{min(players, PLAYERS_PER_POLL)} of {players} league players' own games asked of OpenDota",
         "why": why(players > PLAYERS_PER_POLL and f"{players - PLAYERS_PER_POLL} wait for later polls: "
                                                   f"{PLAYERS_PER_POLL} a poll, one OpenDota call each")},
        {"key": "stats", "name": "Stats of parsed matches",
         "planned": f"the stats of {derive} parsed matches computed", "why": []},
    ]]  # fmt: skip


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


def refresh_players(engine: Engine, account_ids: list[int]) -> int:
    """The games outside the league of those of these players never asked for, now rather than at the poller's pace,
    and from then on the replays of those games young enough (see poll_once). Returns how many players were asked
    for; an OpenDota failure raises httpx.HTTPError, keeping those before it."""
    with BUSY, Session(engine) as session, httpx.Client() as client:
        unlisted = [a for a in account_ids if session.get(PlayerGameList, a) is None]
        try:
            for i, account_id in enumerate(unlisted, 1):
                doing(f"asking OpenDota for the last games of player {account_id} ({i} of {len(unlisted)}), for the site")
                fetch_player_games(session, client, account_id)
        finally:
            doing("waiting for the next poll")
        # their usual games' replays are fetched from now on, at the poller's pace
        for listed in session.scalars(select(PlayerGameList).where(PlayerGameList.account_id.in_(account_ids))):
            listed.replays_wanted = True
        session.commit()
        return len(unlisted)


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
