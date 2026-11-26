"""The settings page's values in .env, the download cap, the poller's pause and interval, and the data it removes."""
import os
import threading
import time
import uuid
import winreg
from compression import zstd

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from dotanalyst import poll, replay, save_env, settings
from dotanalyst.db import Base, Derived, Match
from dotanalyst.replay import Throttle

DAY = 86400
VARIABLES = ["DOWNLOAD_LIMIT_KBPS", "CHECK_SECONDS", "REPLAY_MAX_AGE_DAYS", "AUTO_UPDATE", "POLL_PAUSED", "MAIN_ACCOUNT",
             "STEAM_ALT_USER", "STEAM_ALT_PASSWORD", "HIDDEN", "DOTA_REPLAY_DIR"]  # fmt: skip


@pytest.fixture(autouse=True)
def own_env(tmp_path, monkeypatch):
    """Each test writes a .env of its own, in an empty folder, and sees none of the real settings."""
    monkeypatch.chdir(tmp_path)
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def engine():
    # one connection for every thread: the recompute runs on its own
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    return engine


def add_match(session: Session, match_id: int, age_days: float, state: str = "parsed") -> None:
    session.add(Match(match_id=match_id, match_seq_num=match_id, start_time=int(time.time() - age_days * DAY), duration=1,
                      radiant_win=True, game_mode=22, lobby_type=7, cluster=1, raw_json={}, replay_state=state))  # fmt: skip
    session.commit()


def test_unset_or_broken_values_count_as_the_defaults(monkeypatch):
    assert settings.number("max_age_days") == 90 and settings.number("download_limit") == 0
    assert settings.flag("auto_update") and not settings.flag("paused")
    monkeypatch.setenv("REPLAY_MAX_AGE_DAYS", "lots")  # edited by hand
    monkeypatch.setenv("CHECK_SECONDS", "3")  # below the poller's own 10 seconds
    assert settings.number("max_age_days") == 90 and settings.number("check_seconds") == 10


@pytest.mark.parametrize(
    "name, value",
    [("max_age_days", 101), ("max_age_days", "30"), ("download_limit", -1), ("paused", 1), ("hidden", "Profile.laning"),
     ("hidden", "a,,b"), ("alt_password", "x\nAUTO_UPDATE=0"), ("main_account", "12a"), ("replay_dir", "no such folder"),
     ("start_with_windows", True), ("colour", "red")],
)  # fmt: skip
def test_values_a_setting_does_not_take_are_refused(name, value):
    with pytest.raises(ValueError):
        settings.check(name, value)


def test_a_change_is_kept_in_env_and_counts_at_once(tmp_path):
    settings.change("max_age_days", 30)
    settings.change("paused", True)
    settings.change("hidden", "profile.laning,filters.role")
    settings.change("replay_dir", "")  # the setup's "don't use my replays"
    assert settings.number("max_age_days") == 30 and settings.flag("paused")
    lines = (tmp_path / ".env").read_text().splitlines()
    assert lines == ["REPLAY_MAX_AGE_DAYS=30", "POLL_PAUSED=1", "HIDDEN=profile.laning,filters.role", "DOTA_REPLAY_DIR="]
    settings.change("replay_dir", None)  # back to Steam's own folder: the line goes
    assert "DOTA_REPLAY_DIR" not in (tmp_path / ".env").read_text()
    assert settings.values()["replay_dir"] is None and settings.values()["hidden"] == "profile.laning,filters.role"


def test_the_password_is_shown_only_as_whether_there_is_one():
    settings.change("alt_password", "hunter2")
    assert settings.values()["alt_password"] is True


def test_save_env_none_takes_the_variable_out(tmp_path, monkeypatch):
    env = tmp_path / "x.env"
    env.write_text("A=1\nDA_GONE=2\n")
    monkeypatch.setenv("DA_GONE", "2")
    save_env("DA_GONE", None, env)
    assert env.read_text() == "A=1\n" and "DA_GONE" not in os.environ


def test_the_throttle_keeps_every_download_together_under_the_cap():
    now, slept = [0.0], []
    throttle = Throttle(clock=lambda: now[0], sleep=slept.append)
    throttle.take(500, 0)  # no cap
    throttle.take(500, 1000)  # half a second's worth
    throttle.take(500, 1000)  # another download's chunk at the same moment queues behind it
    assert slept == [0.5, 1.0]
    now[0] = 60  # idle for a minute: no allowance saved up, the next chunk waits its own share only
    throttle.take(1000, 1000)
    assert slept[-1] == 1.0


def test_a_download_waits_as_the_settings_cap_says(tmp_path, monkeypatch):
    body = zstd.compress(b"replay" * 1000)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)))
    now, slept = [0.0], []
    monkeypatch.setattr(replay, "THROTTLE", Throttle(clock=lambda: now[0], sleep=slept.append))
    assert replay.download_replay("http://replay1.valve.net/570/7_1.dem.bz2", tmp_path / "7.dem", client)
    assert slept == []  # no cap
    settings.change("download_limit", 1)  # 1 KB/s
    assert replay.download_replay("http://replay1.valve.net/570/7_1.dem.bz2", tmp_path / "7.dem", client)
    assert sum(slept) == pytest.approx(len(body) / 1024)


def test_new_games_are_looked_for_at_the_settings_interval():
    assert poll.wait_after("accounts") == poll.LOOP_SECONDS
    settings.change("check_seconds", 300)
    assert poll.wait_after("accounts") == poll.wait_after("leagues") == 300
    assert poll.wait_after("downloads") == poll.LOOP_SECONDS  # replays already wanted are not held back


class Rounds:
    """A stop event that ends the loop after `n` waits, and remembers how long each was."""

    def __init__(self, n: int) -> None:
        self.n, self.waits = n, []

    def is_set(self) -> bool:
        return len(self.waits) >= self.n

    def wait(self, seconds: float) -> None:
        self.waits.append(seconds)


def test_a_paused_poller_only_waits(engine, monkeypatch):
    ran = []
    monkeypatch.setattr(poll, "run_step", lambda key, *rest: ran.append(key))
    settings.change("paused", True)
    poll.loop(engine, "accounts", Rounds(2))
    assert ran == []
    settings.change("paused", False)
    stop = Rounds(2)
    poll.loop(engine, "accounts", stop)
    assert ran == ["accounts", "accounts"] and stop.waits == [poll.LOOP_SECONDS] * 2


def test_the_max_age_moves_the_download_window(engine):
    with Session(engine) as session:
        add_match(session, 1, age_days=40, state="none")
        due = lambda: [m for m, _ in session.execute(poll.due(time.time(), 0))]  # noqa: E731
        assert due() == [1]
        settings.change("max_age_days", 30)
        assert due() == []


def test_old_parser_output_is_removed_and_its_stats_stay(engine, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    with Session(engine) as session:
        for match_id, age in ((1, 400), (2, 200), (3, 10)):
            add_match(session, match_id, age)
            (raw / f"{match_id}.jsonl.gz").write_bytes(b"x" * 100)
        add_match(session, 4, 500)  # its output went before
        assert settings.remove_parser_output(session, 180, raw) == {"files": 2, "bytes": 200}
        assert sorted(p.name for p in raw.iterdir()) == ["3.jsonl.gz"]
        assert session.get(Match, 1).replay_state == "parsed"  # so it is never downloaded again


def test_a_recompute_counts_its_matches_and_runs_once_at_a_time(engine):
    with Session(engine) as session:
        add_match(session, 1, 1)
        add_match(session, 2, 1)
        add_match(session, 3, 1, state="none")
    gate = threading.Event()

    def recompute(session, on_match):
        gate.wait(5)
        on_match()
        on_match()
        return 1, ["match 2: no log"]

    assert settings.start_recompute(engine, recompute)
    assert settings.RECOMPUTE["running"] and settings.RECOMPUTE["total"] == 2
    assert not settings.start_recompute(engine, recompute)  # the first is still at work
    gate.set()
    for _ in range(100):
        if not settings.RECOMPUTE["running"]:
            break
        time.sleep(0.02)
    assert settings.RECOMPUTE | {"finished": None} == {"running": False, "done": 2, "total": 2, "problems": 1, "finished": None}


def test_start_with_windows_writes_and_removes_the_run_value():
    key = rf"Software\DotAnalystTest-{uuid.uuid4().hex}"  # made up, deleted again
    try:
        settings.set_run_at_login(True, key, exe=r"C:\Apps\DotAnalyst.exe")
        assert settings.run_at_login(key)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            assert winreg.QueryValueEx(k, "DotAnalyst")[0] == r'"C:\Apps\DotAnalyst.exe" --tray'
        settings.set_run_at_login(False, key)
        settings.set_run_at_login(False, key)  # off twice is fine
        assert not settings.run_at_login(key)
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
