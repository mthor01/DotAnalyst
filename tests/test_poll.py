import bz2
import gzip
import os
import time
from compression import zstd
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst.db import Base, Match
from dotanalyst.poll import poll_once

FIXTURES = Path(__file__).parent / "fixtures"
GOOD = 8810606282
LOG = gzip.decompress((FIXTURES / f"{GOOD}.jsonl.gz").read_bytes())
OPENDOTA = (FIXTURES / "opendota_match.json").read_bytes()  # a real response; its replay_salt is 519105714
WRONG_LOG, STILL_DOWNLOADING, NOT_STORED = 11, 22, 33
REPLAY = b"replay"
CLUSTER = 444
DAY = 86400


def add_match(session: Session, match_id: int, age_days: float = 0) -> None:
    session.add(
        Match(
            match_id=match_id, match_seq_num=match_id, start_time=int(time.time() - age_days * DAY), duration=1,
            radiant_win=True, game_mode=22, lobby_type=7, cluster=CLUSTER, raw_json={},
        )
    )
    session.commit()


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def network(calls: list[str], opendota=(404, b""), valve=(404, b"")) -> httpx.Client:
    """OpenDota, Valve's replay servers and the parser; the parser always returns the log of GOOD."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "api.opendota.com":
            return httpx.Response(opendota[0], content=opendota[1])
        if request.url.host.endswith(".valve.net"):
            return httpx.Response(valve[0], content=valve[1])
        assert request.url.host == "localhost"
        assert request.content == REPLAY  # the parser gets the decompressed file
        return httpx.Response(200, content=LOG)

    return httpx.Client(transport=httpx.MockTransport(handler))


def to(host: str, calls: list[str]) -> list[str]:
    return [url for url in calls if host in url]


def test_poll_parses_downloaded_replays_of_stored_matches(session, tmp_path):
    for match_id in (GOOD, WRONG_LOG, STILL_DOWNLOADING):
        add_match(session, match_id)
    replays = tmp_path / "replays"
    replays.mkdir()
    an_hour_ago = time.time() - 3600
    for name in (GOOD, WRONG_LOG, NOT_STORED, "notes"):
        (replays / f"{name}.dem").write_bytes(REPLAY)
        os.utime(replays / f"{name}.dem", (an_hour_ago, an_hour_ago))
    (replays / f"{STILL_DOWNLOADING}.dem").write_bytes(b"half a replay")
    calls = []
    client = network(calls)

    assert poll_once(session, client, "", replays, tmp_path) == (0, 1)
    assert [p.name for p in (tmp_path / "raw").iterdir()] == [f"{GOOD}.jsonl.gz"]
    assert session.get(Match, GOOD).replay_state == "parsed"
    assert session.get(Match, WRONG_LOG).replay_state == "failed"
    assert session.get(Match, STILL_DOWNLOADING).replay_state == "pending"  # no replay online either
    assert len(to("localhost", calls)) == 2  # not the unknown match, the fresh file or the non-numeric name

    assert poll_once(session, client, "", replays, tmp_path) == (0, 0)
    assert len(to("localhost", calls)) == 2  # parsed and failed replays are not sent again


def test_poll_survives_a_missing_replay_folder(session, tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path) == (0, 0)


def test_poll_downloads_and_parses_replays(session, tmp_path):
    add_match(session, GOOD)
    add_match(session, WRONG_LOG, age_days=1)  # the parser will return another match's log for it
    calls = []
    client = network(calls, opendota=(200, OPENDOTA), valve=(200, zstd.compress(REPLAY)))

    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path) == (0, 1)
    assert to("valve.net", calls) == [
        f"http://replay{CLUSTER}.valve.net/570/{GOOD}_519105714.dem.bz2",
        f"http://replay{CLUSTER}.valve.net/570/{WRONG_LOG}_519105714.dem.bz2",
    ]
    assert session.get(Match, GOOD).replay_state == "parsed"
    assert session.get(Match, WRONG_LOG).replay_state == "failed"
    assert [p.name for p in (tmp_path / "raw").iterdir()] == [f"{GOOD}.jsonl.gz"]  # nothing for the failed parse
    assert list((tmp_path / "tmp").iterdir()) == []  # downloaded .dem files are deleted either way

    calls.clear()
    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path) == (0, 0)
    assert calls == []  # parsed and failed matches are never fetched again


def test_match_without_a_replay_is_retried_hourly_and_given_up_after_14_days(session, tmp_path):
    recent, old, too_old = 1, 2, 3
    add_match(session, recent, age_days=13)
    add_match(session, old, age_days=15)
    add_match(session, too_old, age_days=31)  # outside the download window: never asked about
    calls = []
    client = network(calls)  # OpenDota knows neither match

    def poll() -> int:
        calls.clear()
        poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
        return len(to("opendota", calls))

    assert poll() == 2
    assert session.get(Match, recent).replay_state == "pending"
    assert session.get(Match, old).replay_state == "unavailable"
    assert session.get(Match, too_old).replay_state == "none"
    assert poll() == 0  # tried less than an hour ago

    for match in (session.get(Match, recent), session.get(Match, old)):
        match.replay_tried_at -= 3601
    session.commit()
    assert poll() == 1  # the pending one again; the unavailable one never


def test_salt_is_asked_for_once_even_if_the_download_has_to_be_repeated(session, tmp_path):
    add_match(session, GOOD)
    calls = []
    client = network(calls, opendota=(200, OPENDOTA))  # a salt, but Valve has no file yet

    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
    session.get(Match, GOOD).replay_tried_at -= 3601
    session.commit()
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)

    assert len(to("valve.net", calls)) == 2
    assert len(to("opendota", calls)) == 1
    assert session.get(Match, GOOD).replay_state == "pending"


@pytest.mark.parametrize(
    "body",
    [zstd.compress(os.urandom(4096))[:2000], bz2.compress(os.urandom(4096))[:2000], b"<html>not an archive</html>"],
    ids=["zstd cut short", "bz2 cut short", "not an archive"],
)
def test_a_broken_download_is_retried_not_parsed(session, tmp_path, body):
    add_match(session, GOOD)
    calls = []
    client = network(calls, opendota=(200, OPENDOTA), valve=(200, body))

    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path) == (0, 0)
    assert to("localhost", calls) == []
    assert session.get(Match, GOOD).replay_state == "pending"
    assert list((tmp_path / "tmp").iterdir()) == []
