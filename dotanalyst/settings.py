"""The settings page. Its values live in .env beside the Steam key (save_env), so the server, the poller and the
desktop app read them the way they read the key, and a change counts from the next time it is read; see Settings in
IMPLEMENTATION.md. Also what the page does to the stored data: removing old parser output, recomputing the stats."""
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from . import save_env
from .db import DATA, Match

# name on the page -> (variable in .env, default, the check a new value must pass)
NUMBERS = {
    "download_limit": ("DOWNLOAD_LIMIT_KBPS", 0, range(0, 1_000_001)),  # KB/s over all downloads together; 0: no cap
    "check_seconds": ("CHECK_SECONDS", 10, range(10, 86_401)),  # between two looks for new matches and league games
    "max_age_days": ("REPLAY_MAX_AGE_DAYS", 90, range(1, 101)),  # replays younger than this are downloaded
}
FLAGS = {"auto_update": ("AUTO_UPDATE", True), "paused": ("POLL_PAUSED", False)}
TEXTS = {
    "main_account": ("MAIN_ACCOUNT", re.compile(r"\d{0,10}")),  # "" for none
    "alt_user": ("STEAM_ALT_USER", re.compile(r"[A-Za-z0-9_]{0,64}")),
    "alt_password": ("STEAM_ALT_PASSWORD", re.compile(r"[^\r\n]{0,200}")),
    "hidden": ("HIDDEN", re.compile(r"([a-z0-9.]+(,[a-z0-9.]+)*)?")),  # the design page's hidden parts, by id
}
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"  # the setup's "start with Windows" writes the same value


def number(name: str) -> int:
    """A number setting; a value edited by hand into something else counts as the default."""
    variable, default, allowed = NUMBERS[name]
    try:
        value = int(os.environ.get(variable, default))
    except ValueError:
        return default
    return value if value in allowed else default


def flag(name: str) -> bool:
    variable, default = FLAGS[name]
    return os.environ.get(variable, "1" if default else "0") != "0"


def text(name: str) -> str:
    return os.environ.get(TEXTS[name][0], "")


def check(name: str, value: object) -> None:
    """Raise ValueError, saying what is wrong, when the page sends a value a setting does not take."""
    if name in NUMBERS:
        allowed = NUMBERS[name][2]
        if type(value) is not int or value not in allowed:
            raise ValueError(f"{name} takes a whole number from {allowed.start} to {allowed.stop - 1}")
    elif name in FLAGS or name == "start_with_windows":
        if type(value) is not bool:
            raise ValueError(f"{name} is on or off")
        if name == "start_with_windows" and not getattr(sys, "frozen", False):
            raise ValueError("only the installed app starts with Windows")
    elif name in TEXTS:
        if not isinstance(value, str) or not TEXTS[name][1].fullmatch(value):  # also keeps a line break out of .env
            raise ValueError(f"{name} does not take {value!r}")
    elif name == "replay_dir":  # None: Steam's own folder; "": none; else a folder that is there
        if value is not None and not (isinstance(value, str) and "\n" not in value and (not value or Path(value).is_dir())):
            raise ValueError(f"{value} is not a folder")
    else:
        raise ValueError(f"there is no setting {name}")


def change(name: str, value) -> None:
    """Keep one value from the page, once check passed it."""
    check(name, value)
    if name in NUMBERS:
        save_env(NUMBERS[name][0], str(value))
    elif name in FLAGS:
        save_env(FLAGS[name][0], "1" if value else "0")
    elif name in TEXTS:
        save_env(TEXTS[name][0], value)
    elif name == "replay_dir":
        save_env("DOTA_REPLAY_DIR", value)
    else:
        set_run_at_login(value)


def run_at_login(key: str = RUN_KEY) -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.QueryValueEx(k, "DotAnalyst")
        return True
    except FileNotFoundError:
        return False


def set_run_at_login(on: bool, key: str = RUN_KEY, exe: str = sys.executable) -> None:
    """Start the installed app in the tray at login, or not; the uninstaller removes the value as well."""
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        if on:
            winreg.SetValueEx(k, "DotAnalyst", 0, winreg.REG_SZ, f'"{exe}" --tray')
        else:
            try:
                winreg.DeleteValue(k, "DotAnalyst")
            except FileNotFoundError:
                pass


def values() -> dict:
    """Everything the page shows; the password only as whether there is one."""
    installed = getattr(sys, "frozen", False)
    return {
        **{name: number(name) for name in NUMBERS},
        **{name: flag(name) for name in FLAGS},
        **{name: text(name) for name in TEXTS if name != "alt_password"},
        "alt_password": bool(text("alt_password")),
        "steam_key": bool(os.environ.get("STEAM_API_KEY")),
        "replay_dir": os.environ.get("DOTA_REPLAY_DIR"),
        "start_with_windows": run_at_login() if installed else None,  # None: not the installed app, nothing to start
        "data_folder": str(Path.cwd()),
    }


def remove_parser_output(session: Session, days: int, raw_dir: Path = DATA / "raw") -> dict:
    """Delete the parser output of matches played more than `days` ago. Their stats stay, and the replay is never
    fetched again; only recomputing and the match page's replay map need the output. Returns files and bytes freed."""
    before = time.time() - days * 86400
    files = size = 0
    for match_id in session.scalars(select(Match.match_id).where(Match.start_time < before)):
        path = raw_dir / f"{match_id}.jsonl.gz"
        try:
            size += path.stat().st_size
            path.unlink()
            files += 1
        except FileNotFoundError:
            pass
    return {"files": files, "bytes": size}


# the recompute the page started: it runs for up to an hour, so the page asks how far it got
RECOMPUTE: dict = {"running": False, "done": 0, "total": 0, "problems": 0, "finished": None}


def start_recompute(engine: Engine, recompute: Callable | None = None) -> bool:
    """Rebuild every parsed match's stats on a thread of its own. False when one runs already."""
    if recompute is None:
        from .derive import recompute
    if RECOMPUTE["running"]:
        return False
    with Session(engine) as session:
        total = len(session.scalars(select(Match.match_id).where(Match.replay_state == "parsed")).all())
    RECOMPUTE.update(running=True, done=0, total=total, problems=0, finished=None)

    def counted() -> None:
        RECOMPUTE["done"] += 1

    def run() -> None:
        try:
            with Session(engine) as session:
                _, problems = recompute(session, on_match=counted)
            RECOMPUTE["problems"] = len(problems)
        finally:
            RECOMPUTE.update(running=False, finished=time.time())

    threading.Thread(target=run, name="recompute", daemon=True).start()
    return True
