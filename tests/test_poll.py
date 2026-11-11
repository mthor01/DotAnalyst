import gzip
import os
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst.db import Base, Match
from dotanalyst.poll import poll_once

GOOD = 8810606282
LOG = gzip.decompress((Path(__file__).parent / "fixtures" / f"{GOOD}.jsonl.gz").read_bytes())
WRONG_LOG, STILL_DOWNLOADING, NOT_STORED = 11, 22, 33


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        for match_id in (GOOD, WRONG_LOG, STILL_DOWNLOADING):
            s.add(
                Match(
                    match_id=match_id, match_seq_num=match_id, start_time=0, duration=1, radiant_win=True,
                    game_mode=22, lobby_type=7, cluster=0, raw_json={},
                )
            )
        s.commit()
        yield s


def test_poll_parses_downloaded_replays_of_stored_matches(session, tmp_path):
    replays = tmp_path / "replays"
    replays.mkdir()
    an_hour_ago = time.time() - 3600
    for name in (GOOD, WRONG_LOG, NOT_STORED, "notes"):
        (replays / f"{name}.dem").write_bytes(b"replay")
        os.utime(replays / f"{name}.dem", (an_hour_ago, an_hour_ago))
    (replays / f"{STILL_DOWNLOADING}.dem").write_bytes(b"half a replay")

    posts = []

    def parser(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return httpx.Response(200, content=LOG)  # always the log of GOOD

    client = httpx.Client(transport=httpx.MockTransport(parser))
    raw = tmp_path / "raw"

    assert poll_once(session, client, "", replays, raw) == (0, 1)
    assert [p.name for p in raw.iterdir()] == [f"{GOOD}.jsonl.gz"]
    assert session.get(Match, GOOD).replay_state == "parsed"
    assert session.get(Match, WRONG_LOG).replay_state == "failed"
    assert session.get(Match, STILL_DOWNLOADING).replay_state == "none"
    assert len(posts) == 2  # not the unknown match, the fresh file or the non-numeric name

    assert poll_once(session, client, "", replays, raw) == (0, 0)
    assert len(posts) == 2  # parsed and failed replays are not sent again


def test_poll_survives_a_missing_replay_folder(session, tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path / "raw") == (0, 0)
