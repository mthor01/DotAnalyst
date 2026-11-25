"""The installed app's settings: the folders the setup asked for."""
import uuid
import winreg
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst import poll
from dotanalyst.app import home, installed_settings
from dotanalyst.db import Base, Derived


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_the_replay_dir_defaults_to_steam(monkeypatch):
    monkeypatch.delenv("DOTA_REPLAY_DIR", raising=False)
    assert poll.replay_dir() == poll.REPLAY_DIR


def test_an_empty_replay_dir_turns_the_folder_off(session, tmp_path, monkeypatch):
    monkeypatch.setenv("DOTA_REPLAY_DIR", "")  # the setup's "don't use my replays"
    assert poll.replay_dir() is None
    assert poll.folder_replays(session, None) == []
    folder = next(s for s in poll.steps(session, None, tmp_path, [], lambda m: 0, 0) if s["key"] == "folder")
    assert folder["planned"] == "off: no replay folder"


def test_installed_settings_reads_the_setups_answers():
    key = rf"Software\DotAnalystTest-{uuid.uuid4().hex}"  # made up, deleted again
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, "DataDir", 0, winreg.REG_SZ, r"D:\Dota data")
        winreg.SetValueEx(k, "ReplayDir", 0, winreg.REG_SZ, "")
    try:
        assert installed_settings(key) == {"DataDir": r"D:\Dota data", "ReplayDir": ""}
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
    assert installed_settings(key) == {}


def test_home_is_the_chosen_data_folder_or_app_data(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\x\AppData\Local")
    assert home({}) == Path(r"C:\Users\x\AppData\Local\DotAnalyst")
    assert home({"DataDir": ""}) == Path(r"C:\Users\x\AppData\Local\DotAnalyst")
    assert home({"DataDir": r"D:\Dota data"}) == Path(r"D:\Dota data")
