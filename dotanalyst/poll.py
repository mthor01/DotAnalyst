import logging
import os
import threading
import time
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.orm import Session

from .db import (
    DATA, Account, League, LeagueMatch, Match, MatchPlayer, PlayerGame, PlayerGameList, PlayerMinute, PlayerName,
)  # fmt: skip
from . import catalog, liquipedia, settings
from .derive import derive_match
from .opendota import fetch_player_games, player_games, store_player_games, unlisted_players, usual_match
from .replay import (
    DOWNLOADED, DOWNLOADING, PARSER_URL, ReplayError, download_and_parse, fetch_replay, mark_tried, opendota_match, parse_dem,
    max_age_days, replay_complete, settle, steam_salts,
)  # fmt: skip
from .steam import call, store_match, sync, sync_leagues

log = logging.getLogger("uvicorn.error")  # the logger uvicorn already prints
REPLAY_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\replays")
LOOP_SECONDS = 10  # each step looks for work this long after its last round ended
RETRY_SECONDS = 10  # an unsalted retry costs one OpenDota call
# replays downloaded and parsed at once: one, as parallel downloads split the line and Valve's replay CDN cuts off a
# download from its storage that runs past ~45-80 s (measured November 2026)
WORKERS = 1
SALTS_PER_POLL = 10  # asked of Valve in one login, which allows the second account about 100 a day
# shortcut: these three are forgotten on restart, so each is tried once more per run; store them if that adds up
NO_MATCH: set[int] = set()  # usual games OpenDota does not know
ASKED: set[int] = set()  # matches whose salt Valve was asked for, whatever it answered
NO_STATS: set[int] = set()  # parsed matches whose stats failed
# for the queue page and the progress bar; kept in memory only, so a restart starts them empty
RUNNING: dict[str, dict] = {}  # per step with work right now: what it does, since when, how far it is
WORKING: set[int] = set()  # matches a step downloads, parses or computes right now
_claims = threading.Lock()
EVENTS: deque[dict] = deque(maxlen=200)
CHECKED: dict[str, float] = {}  # per step: when its last round ended, with work or without
FINISHED: Counter[str] = Counter()  # per step: what its rounds finished since the server started (see run_step)
# what takes room in the data folder, in the order the storage chart colours it; everything else is "Other"
STORAGE = {"raw": "Parser output", "dotanalyst.db": "Database", "opendota": "OpenDota answers",
           "steam": "Steam answers", "tmp": "Replays being fetched", "leagues": "Tournament previews"}  # fmt: skip
LIVE = "IDOTA2Match_570/GetLiveLeagueGames/v1/"
LIVE_SECONDS = 300  # Steam's live league games, for the tournament browser's Live now
CATALOG_SECONDS = 600  # the catalog step looks this often; OpenDota's list itself is read once a day
LOOKUPS = 30  # Liquipedia lookups in one catalog round, 2 seconds apart


@dataclass
class Setup:
    key: str  # STEAM_API_KEY; without it Steam is not asked
    replay_dir: Path | None  # the Dota client's replay folder; None: the user chose not to use it
    data: Path = DATA
    alt: bool = False  # whether the second Steam account asks Valve for salts
    retry_seconds: int = RETRY_SECONDS
    newest_only: bool = True  # read Steam's lists only until a page that is all stored


def doing(step: str, what: str, done: int | None = None, total: int | None = None) -> None:
    since = RUNNING.get(step, {}).get("since", time.time())
    RUNNING[step] = {"doing": what, "since": since, "done": done, "total": total}  # replaced whole: others read it


def claim(match_id: int) -> bool:
    """Mark a match as worked on, unless another step already is: two never download or derive the same one."""
    with _claims:
        if match_id in WORKING:
            return False
        WORKING.add(match_id)
        return True


def release(match_id: int) -> None:
    WORKING.discard(match_id)


def event(match_id: int | None, message: str, warn: bool = True) -> None:
    if warn:
        log.warning("match %s: %s", match_id, message)
    EVENTS.append({"at": time.time(), "match_id": match_id, "message": message})


def wanted(now: float):
    """Matches whose replay the poller still wants, whenever it next tries them."""
    return or_(
        Match.replay_state == "pending",
        and_(Match.replay_state == "none", Match.start_time > now - max_age_days() * 86400),
    )


def due(now: float, retry_seconds: int):
    """Wanted matches whose try is due: never tried first, so a new match is not stuck behind retries; each group
    newest first."""
    return (
        select(Match.match_id, Match.cluster)
        # a match already tried is followed up whatever its age, so it cannot stay pending for ever
        .where(wanted(now), or_(Match.replay_tried_at.is_(None), Match.replay_tried_at < now - retry_seconds))
        .order_by(Match.replay_tried_at.is_not(None), Match.start_time.desc())
    )


def usual_waiting(now: float):
    """Usual games of a checked team's players young enough to become matches and not yet stored, newest first."""
    return (
        select(PlayerGame.match_id).distinct()
        .join(PlayerGameList, and_(PlayerGameList.account_id == PlayerGame.account_id, PlayerGameList.replays_wanted))
        .where(PlayerGame.start_time > now - max_age_days() * 86400, PlayerGame.match_id.not_in(select(Match.match_id)))
        .where(PlayerGame.match_id.not_in(NO_MATCH))
        .order_by(PlayerGame.match_id.desc())
    )  # fmt: skip


def folder_replays(session: Session, replay_dir: Path | None) -> list[Path]:
    """The .dem files in the Dota client folder of stored matches that have no parse yet."""
    found = []
    for dem in sorted(replay_dir.glob("*.dem")) if replay_dir and replay_dir.is_dir() else []:
        match = session.get(Match, int(dem.stem)) if dem.stem.isdigit() else None
        if match is not None and match.replay_state not in ("parsed", "failed"):
            found.append(dem)
    return found


def accounts_step(session: Session, client: httpx.Client, setup: Setup) -> int:
    """New matches of the tracked accounts. Returns how many."""
    if not setup.key:
        return 0
    doing("accounts", "asking Steam for new matches of the accounts")
    return sum(count or 0 for count in sync(session, client, setup.key, setup.newest_only).values())


def leagues_step(session: Session, client: httpx.Client, setup: Setup) -> int:
    """New games of the tracked tournaments. Returns how many."""
    new = 0
    if setup.key:
        doing("leagues", "asking Steam for new league games")
        new = sync_leagues(session, client, setup.key, setup.newest_only)
    # a league game young enough to download becomes a match like any other: its replay is fetched and its stats
    # computed by the steps after. No tracked account plays in it, so it joins nobody's stats
    recent = select(LeagueMatch.raw_json).where(
        LeagueMatch.start_time > time.time() - max_age_days() * 86400, LeagueMatch.match_id.not_in(select(Match.match_id)),
        LeagueMatch.league_id.in_(select(League.league_id)),  # a tournament taken off the list downloads no more
    )
    young = session.scalars(recent).all()
    for raw in young:
        store_match(session, raw)
    session.commit()
    return new


def usual_step(session: Session, client: httpx.Client, setup: Setup) -> int:
    """The usual games of a checked team's players become matches too, from OpenDota's answer, which also holds the
    salt their download needs; they join nobody's stats either, only the players' ward maps. Returns how many."""
    waiting = session.scalars(usual_waiting(time.time())).all()
    done = 0
    for match_id in waiting:
        doing("usual", f"asking OpenDota for usual game {match_id}", done, len(waiting))
        try:
            found = usual_match(opendota_match(match_id, client, setup.data / "opendota"), match_id)
        except httpx.HTTPError as error:
            event(match_id, f"usual match from OpenDota, the rest waits for the next round: {error!r}")
            break
        if found is None:
            NO_MATCH.add(match_id)
            event(match_id, "OpenDota does not know this usual match", warn=False)
            continue
        store_match(session, found)
        session.commit()
        done += 1
    return done


def folder_step(session: Session, client: httpx.Client, setup: Setup) -> int:
    """Parse the replays the Dota client downloaded. Returns how many were parsed."""
    in_folder = folder_replays(session, setup.replay_dir)
    # a file the Dota client is still writing would parse as truncated and be marked failed for good
    ready = [dem for dem in in_folder if replay_complete(dem)]
    done = 0
    for dem in ready:
        match_id = int(dem.stem)
        if not claim(match_id):
            continue
        doing("folder", f"parsing {dem.name} from the Dota client folder", done, len(ready))
        try:
            parsed = parse_dem(dem, match_id, client, setup.data / "raw")
            settle(session, session.get(Match, match_id), "parsed" if parsed else "failed")
            done += 1
            event(match_id, "parsed from the Dota client folder", warn=False)
        except (ReplayError, OSError, httpx.HTTPError) as error:
            event(match_id, f"{dem.name} from the Dota client folder: {error!r}")
        finally:
            release(match_id)
    return done


def salts_step(session: Session, client: httpx.Client, setup: Setup) -> int:
    """The second Steam account asks Valve for the salts of due downloads; OpenDota is asked for what that leaves
    open. Each match is asked for once a run, so a failed login is not tried again every round. Returns how many
    salts Valve gave."""
    if not setup.alt:
        return 0
    known = steam_salts([], setup.data)
    asked = [
        match_id for match_id, _ in session.execute(due(time.time(), setup.retry_seconds))
        if match_id not in known and match_id not in ASKED
        and not (setup.data / "opendota" / f"{match_id}.json.gz").exists()  # OpenDota gave its salt already
    ][:SALTS_PER_POLL]  # fmt: skip
    if not asked:
        return 0
    doing("salts", f"asking Valve for {len(asked)} replay salts with the second Steam account")
    ASKED.update(asked)
    try:
        salts = steam_salts(asked, setup.data)
    except ReplayError as error:
        event(None, f"replay salts from Steam: {error}; asking OpenDota instead")
        return 0
    return sum(m in salts for m in asked)


def downloads_step(session: Session, client: httpx.Client, setup: Setup) -> int:
    """Download and parse every due replay, WORKERS at a time; a match that becomes due meanwhile joins at once.
    A worker gets plain ids and touches no database: its result comes back here, and this thread alone writes it.
    Returns how many were parsed."""
    pool = ThreadPoolExecutor(WORKERS)
    jobs: dict[Future, int] = {}
    seen: set[int] = set()  # taken this round, so a replay that was not there waits for the next
    salts: dict[int, int] = {}
    waiting: list = []
    done, stopped = 0, False
    try:
        while True:
            if not stopped and len(jobs) < WORKERS:
                salts = steam_salts([], setup.data)  # read again: the salts step adds to it meanwhile
                # parsed from the folder instead
                skip = seen | {int(d.stem) for d in folder_replays(session, setup.replay_dir) if replay_complete(d)}
                waiting = [row for row in session.execute(due(time.time(), setup.retry_seconds)).all() if row[0] not in skip]
                for match_id, cluster in waiting:
                    if len(jobs) >= WORKERS:
                        break
                    if not claim(match_id):
                        continue
                    seen.add(match_id)
                    future = pool.submit(download_and_parse, match_id, cluster, client, setup.data, salts.get(match_id))
                    jobs[future] = match_id
            if not jobs:
                break
            # of: parsed this round + under way + still waiting; one that fails drops out
            total = done + len(jobs) + sum(m not in seen for m, _ in waiting)
            doing("downloads", f"downloading and parsing match {', '.join(map(str, jobs.values()))}", done, total)
            finished, _ = wait(jobs, return_when=FIRST_COMPLETED)
            for future in finished:
                match_id = jobs.pop(future)
                try:
                    if future.cancelled():
                        continue
                    match = session.get(Match, match_id)
                    mark_tried(session, match)  # also when it failed, so a match that keeps erroring waits like any other
                    if settle(session, match, future.result()):
                        done += 1
                        event(match_id, "downloaded and parsed", warn=False)
                    else:
                        salted = match_id in salts or (setup.data / "opendota" / f"{match_id}.json.gz").exists()
                        why = "Valve has no file for it" if salted else "no salt: OpenDota does not know it"
                        event(match_id, f"no replay yet ({why}), now {match.replay_state}", warn=False)
                except ReplayError as error:
                    event(match_id, str(error))
                # Valve's replay servers often cut a download off midway: only that match waits for its retry
                except (httpx.RemoteProtocolError, httpx.ReadError) as error:
                    event(match_id, f"download cut off, tried again later: {error!r}")
                except (OSError, httpx.HTTPError) as error:  # a server or the disk is in trouble
                    event(match_id, f"download stopped, the rest waits for the next round: {error!r}")
                    stopped = True
                    for other in jobs:
                        other.cancel()
                finally:
                    release(match_id)
    finally:
        pool.shutdown(cancel_futures=True)  # an error above must not wait for hundreds of downloads
        for match_id in jobs.values():
            release(match_id)
    return done


def players_step(session: Session, client: httpx.Client, setup: Setup) -> int:
    """The league players' own games, for their role wheel on the team page: the list only, never a replay."""
    unlisted = unlisted_players(session, 10**9)
    done = 0
    for account_id in unlisted:
        doing("players", f"asking OpenDota for the last games of player {account_id}", done, len(unlisted))
        try:
            store_player_games(session, account_id, player_games(client, account_id))
            done += 1
        except httpx.HTTPError as error:
            session.rollback()
            event(None, f"games of player {account_id}, the rest waits for the next round: {error!r}")
            break
    return done


def stats_step(session: Session, client: httpx.Client, setup: Setup) -> int:
    """Compute the stats of every parsed match that has none. Returns how many."""
    waiting = [m for m in session.scalars(without_stats()).all() if m not in NO_STATS]
    done = 0
    for match_id in waiting:
        if not claim(match_id):  # a replay asked for from the site computes its own
            continue
        doing("stats", f"computing the stats of match {match_id}", done, len(waiting))
        try:
            derive_match(session, match_id, setup.data / "raw")
            done += 1
        except Exception as error:  # a log one derivation cannot handle must not stop the others
            session.rollback()
            NO_STATS.add(match_id)
            log.exception("replay stats of match %s failed", match_id)
            event(match_id, f"stats failed: {error!r}", warn=False)
        finally:
            release(match_id)
    return done


def live_step(session: Session, client: httpx.Client, setup: Setup) -> int:
    """Note the leagues playing right now, amateur ones too, from Steam's live league games. Returns how many."""
    if not setup.key:
        return 0
    doing("live", "asking Steam for the league games played right now")
    return catalog.record_live(session, call(client, setup.key, LIVE).get("games", []), time.time())


def catalog_step(session: Session, client: httpx.Client, setup: Setup, now: float | None = None) -> int:
    """OpenDota's league list once a day, then Liquipedia for the leagues of Explore and the subscribed ones that it
    was never asked about, or not for a week while they play. Returns the Liquipedia lookups."""
    now = now or time.time()
    doing("catalog", "reading OpenDota's league list")
    catalog.refresh(session, client, now)
    found = catalog.explore(session, now)
    wanted = [r["league_id"] for r in found["live"] + found["big"]] + list(session.scalars(select(League.league_id)))
    due = [i for i in dict.fromkeys(wanted) if (row := session.get(catalog.LeagueCatalog, i)) is None or liquipedia.due(row, now)]
    for done, league_id in enumerate(due[:LOOKUPS]):
        doing("catalog", f"asking Liquipedia about league {league_id}", done, min(len(due), LOOKUPS))
        liquipedia.lookup(session, client, league_id, now)
    return min(len(due), LOOKUPS)


# in the order poll_once runs them, which is also the order the queue page lists them
STEP_FUNCS = {
    "accounts": accounts_step, "leagues": leagues_step, "usual": usual_step, "folder": folder_step,
    "salts": salts_step, "downloads": downloads_step, "players": players_step, "stats": stats_step,
    "live": live_step, "catalog": catalog_step,
}  # fmt: skip
BROWSER_STEPS = ("live", "catalog")
LOCKS = {key: threading.Lock() for key in STEP_FUNCS}  # a step and the same work asked for from the site never overlap


def run_step(key: str, session: Session, client: httpx.Client, setup: Setup) -> int:
    try:
        found = STEP_FUNCS[key](session, client, setup)
    finally:
        RUNNING.pop(key, None)  # before FINISHED grows: the queue page adds a running round's count on its own
        CHECKED[key] = time.time()
    FINISHED[key] += found
    return found


def poll_once(
    session: Session, client: httpx.Client, key: str, replay_dir: Path | None, data: Path = DATA, alt: bool = False,
    retry_seconds: int = RETRY_SECONDS, newest_only: bool = False,
) -> tuple[int, int]:  # fmt: skip
    """Every step once, one after the other on this thread (see STEP_FUNCS); the server runs each on its own, see
    start. A replay that was not there is tried again after retry_seconds. Returns (new matches, replays parsed)."""
    if not key:
        log.warning("STEAM_API_KEY is not set, skipping sync")
    setup = Setup(key, replay_dir, data, alt, retry_seconds, newest_only)
    # the tournament browser's steps only serve the site: the server runs them (start), a single run does not
    found = {step: run_step(step, session, client, setup) for step in STEP_FUNCS if step not in BROWSER_STEPS}
    return found["accounts"] + found["leagues"], found["folder"] + found["downloads"]


def setup_from_env(newest_only: bool = True) -> Setup:
    return Setup(
        os.environ.get("STEAM_API_KEY", ""), replay_dir(), alt=bool(os.environ.get("STEAM_ALT_USER")),
        newest_only=newest_only,
    )  # fmt: skip


def loop(engine: Engine, key: str, stop: threading.Event) -> None:
    """One step, over and over: a round does all the work there is, then the step looks again LOOP_SECONDS later
    (the looks for new matches and league games after the settings' interval). Paused, it only waits."""
    newest_only = False  # the first round reads Steam's whole lists, to pick up what an interrupted run left out
    while not stop.is_set():
        if not settings.flag("paused"):
            try:
                with LOCKS[key], Session(engine) as session, httpx.Client() as client:
                    run_step(key, session, client, setup_from_env(newest_only))
                newest_only = True
            except Exception:  # one bad round must not end the step
                log.exception("poll step %s failed, next round in %d s", key, LOOP_SECONDS)
        stop.wait(wait_after(key))


def wait_after(key: str) -> int:
    """Seconds between two rounds of a step: Steam is asked for new games at the settings' interval."""
    if key in ("live", "catalog"):
        return LIVE_SECONDS if key == "live" else CATALOG_SECONDS
    return max(LOOP_SECONDS, settings.number("check_seconds")) if key in ("accounts", "leagues") else LOOP_SECONDS


def start(engine: Engine) -> threading.Event:
    """Run every step on its own thread, side by side; none waits for another. Set the returned event to stop them."""
    if not os.environ.get("STEAM_API_KEY"):
        log.warning("STEAM_API_KEY is not set, skipping sync")
    stop = threading.Event()
    for key in STEP_FUNCS:
        threading.Thread(target=loop, args=(engine, key, stop), name=f"poll-{key}", daemon=True).start()
    return stop


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


def queue(session: Session, replay_dir: Path | None, data: Path = DATA, now: float | None = None) -> dict:
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
        httpx.get(PARSER_URL, timeout=1)  # any answer will do: it shows the parser is up
        parser = True
    except httpx.HTTPError:
        parser = False
    names = whose(session, [m.match_id for m in waiting])
    running = dict(RUNNING)  # a copy: the steps go on changing it
    return {
        "busy": bool(running), "running": running, "now": now, "parser": parser,
        "retry_seconds": RETRY_SECONDS, "loop_seconds": LOOP_SECONDS, "max_age_days": max_age_days(),
        "states": states, "steps": steps(session, replay_dir, data, waiting, next_try, now),
        "storage": storage(data),
        "downloading": list(DOWNLOADING.values()), "downloaded": list(reversed(DOWNLOADED)),
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


def progress(session: Session, now: float | None = None) -> dict:
    """For the progress bar on every page, so it is cheap: what each step with work does now, the matches being
    downloaded, parsed or computed, and per profile and per tournament how many replays are parsed of those it can
    get (parsed + still wanted; replays it gave up on count in neither)."""
    now = now or time.time()
    counts = (func.count().filter(Match.replay_state == "parsed"), func.count().filter(wanted(now)))
    profiles = (
        select(Account.account_id, Account.label, *counts)
        .join(MatchPlayer, MatchPlayer.account_id == Account.account_id).join(Match, Match.match_id == MatchPlayer.match_id)
        .where(Account.active).group_by(Account.account_id).order_by(Account.label, Account.account_id)
    )  # fmt: skip
    tournaments = (
        select(League.league_id, League.name, *counts)
        .join(LeagueMatch, LeagueMatch.league_id == League.league_id).join(Match, Match.match_id == LeagueMatch.match_id)
        .group_by(League.league_id).order_by(League.league_id.desc())
    )  # fmt: skip
    parsed, waiting = session.execute(select(*counts)).one()
    running = dict(RUNNING)  # a copy: the steps go on changing it
    return {
        "busy": bool(running), "running": running, "now": now, "loop_seconds": LOOP_SECONDS,
        "max_age_days": max_age_days(), "working": sorted(WORKING),
        "overall": {"parsed": parsed, "waiting": waiting},
        "profiles": [{"account_id": a, "name": name, "parsed": p, "waiting": w} for a, name, p, w in session.execute(profiles)],
        "tournaments": [{"league_id": i, "name": name, "parsed": p, "waiting": w} for i, name, p, w in session.execute(tournaments)],
    }  # fmt: skip


def steps(session: Session, replay_dir: Path, data: Path, waiting: list[Match], next_try, now: float) -> list[dict]:
    """Each step in its order, in numbers: what its next round has to do and what still waits, what its rounds
    finished since the server started, and when its last round ended (the next starts LOOP_SECONDS later)."""
    key, alt = os.environ.get("STEAM_API_KEY"), os.environ.get("STEAM_ALT_USER")
    accounts = session.scalar(select(func.count()).select_from(Account).where(Account.active))
    leagues = session.scalar(select(func.count()).select_from(League))
    usual = session.scalar(select(func.count()).select_from(usual_waiting(now).subquery()))
    in_folder = folder_replays(session, replay_dir)
    ready = sum(map(replay_complete, in_folder))
    due = [m for m in waiting if next_try(m) <= now]
    later = len(waiting) - len(due)
    known = steam_salts([], data) if alt else {}
    # as salts_step picks them, without its cap of SALTS_PER_POLL a round
    salts = sum(
        m.match_id not in known and m.match_id not in ASKED and not (data / "opendota" / f"{m.match_id}.json.gz").exists()
        for m in due
    )  # fmt: skip
    # shortcut: walks every league game (about 0.2 s on 2000 games) on each refresh of the page; cache it if that grows
    players = len(unlisted_players(session, 10**9))
    derive = session.scalar(select(func.count()).select_from(without_stats().subquery()))

    writing = len(in_folder) - ready
    planned = {  # key: (name, planned, what FINISHED counts)
        "accounts": ("New matches of the accounts", f"{accounts} accounts" if key else "off: no STEAM_API_KEY", "new matches"),
        "leagues": ("New league games", f"{leagues} tournaments" if key else "off: no STEAM_API_KEY", "new games"),
        "usual": ("Usual games of checked players", f"{usual} games", "matches"),
        "folder": ("Replays in the Dota client folder",
                   f"{ready} replays" + (f", {writing} still being written" if writing else "") if replay_dir
                   else "off: no replay folder", "replays"),
        "salts": ("Replay ids from Valve", f"{salts} salts" if alt else "off: no STEAM_ALT_USER", "salts"),
        "downloads": ("Replay downloads and parsing",
                      f"{len(due)} replays" + (f", {later} waiting for a retry" if later else ""), "replays"),
        "players": ("Game lists of league players", f"{players} players", "players"),
        "stats": ("Stats of parsed matches", f"{derive} matches", "matches"),
        "live": ("Leagues playing now", "Steam's live league games" if key else "off: no STEAM_API_KEY", "leagues live"),
        "catalog": ("Tournament list and Liquipedia", "OpenDota's list daily, Liquipedia for Explore", "lookups"),
    }  # fmt: skip
    return [
        # with the running round's own count: a downloads round can last hours
        {"key": k, "name": name, "planned": plan, "finished": f"{FINISHED[k] + (RUNNING.get(k, {}).get('done') or 0)} {what}",
         "checked": CHECKED.get(k)}
        for k, (name, plan, what) in planned.items()
    ]


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
    if not claim(match_id):
        raise ReplayError("the poller is fetching this replay right now; it shows up here once it is parsed")
    try:
        with Session(engine) as session, httpx.Client() as client:
            return request_replay(session, client, match_id, alt=bool(os.environ.get("STEAM_ALT_USER")))
    except (OSError, httpx.HTTPError) as error:
        reason = f"the download or the parser failed ({type(error).__name__}); does the parser answer on port 5600?"
        raise ReplayError(reason) from error
    finally:
        release(match_id)


def replay_dir() -> Path | None:
    """DOTA_REPLAY_DIR, else Steam's default folder; set but empty (the setup's "don't use my replays"): None."""
    folder = os.environ.get("DOTA_REPLAY_DIR")
    return REPLAY_DIR if folder is None else Path(folder) if folder else None


def refresh(engine: Engine) -> dict:
    """New matches of the accounts, asked for from the site; the other steps take them up within LOOP_SECONDS."""
    with LOCKS["accounts"], Session(engine) as session, httpx.Client() as client:
        new = run_step("accounts", session, client, setup_from_env())
        waiting = session.scalar(select(func.count()).select_from(Match).where(Match.replay_state == "pending"))
    return {"matches": new, "waiting": waiting}


def refresh_leagues(engine: Engine) -> dict:
    """New league games, asked for from the site."""
    with LOCKS["leagues"], Session(engine) as session, httpx.Client() as client:
        return {"league_games": sync_leagues(session, client, os.environ.get("STEAM_API_KEY", ""))}


def refresh_players(engine: Engine, account_ids: list[int]) -> int:
    """The games outside the league of those of these players never asked for, now rather than at the poller's pace,
    and from then on the replays of those games young enough (see usual_step). Returns how many players were asked
    for; an OpenDota failure raises httpx.HTTPError, keeping those before it."""
    with LOCKS["players"], Session(engine) as session, httpx.Client() as client:
        unlisted = [a for a in account_ids if session.get(PlayerGameList, a) is None]
        try:
            for i, account_id in enumerate(unlisted):
                doing("players", f"asking OpenDota for the last games of player {account_id}, for the site", i, len(unlisted))
                fetch_player_games(session, client, account_id)
        finally:
            RUNNING.pop("players", None)
        # their usual games' replays are fetched from now on, at the poller's pace
        for listed in session.scalars(select(PlayerGameList).where(PlayerGameList.account_id.in_(account_ids))):
            listed.replays_wanted = True
        session.commit()
        return len(unlisted)
