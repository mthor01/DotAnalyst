import gzip
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst.db import Base, Match
from dotanalyst.replay import ReplayError, epilogue_match_id, parse_replay

MATCH_ID = 8810606282
LOG = gzip.decompress((Path(__file__).parent / "fixtures" / f"{MATCH_ID}.jsonl.gz").read_bytes())
TRUNCATED = LOG[: len(LOG) // 2]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(
            Match(
                match_id=MATCH_ID, match_seq_num=1, start_time=0, duration=1049,
                radiant_win=False, game_mode=22, lobby_type=7, cluster=0, raw_json={},
            )
        )
        s.commit()
        yield s


def parser_returning(body: bytes) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)))


def dem(tmp_path: Path, match_id: int = MATCH_ID) -> Path:
    path = tmp_path / f"{match_id}.dem"
    path.write_bytes(b"not a real replay")
    return path


def test_epilogue_gives_match_id():
    assert epilogue_match_id(LOG) == MATCH_ID


def test_truncated_log_has_no_epilogue():
    assert epilogue_match_id(TRUNCATED) is None
    assert epilogue_match_id(b"") is None


def test_parse_stores_log_and_marks_parsed(session, tmp_path):
    out = parse_replay(session, dem(tmp_path), parser_returning(LOG), tmp_path / "raw")
    assert gzip.decompress(out.read_bytes()) == LOG
    assert session.get(Match, MATCH_ID).replay_state == "parsed"


def test_parsed_match_is_not_sent_again(session, tmp_path):
    parse_replay(session, dem(tmp_path), parser_returning(LOG), tmp_path / "raw")

    def fail(request):
        raise AssertionError("parser was called for an already parsed match")

    client = httpx.Client(transport=httpx.MockTransport(fail))
    parse_replay(session, dem(tmp_path), client, tmp_path / "raw")


def test_incomplete_output_is_rejected(session, tmp_path):
    with pytest.raises(ReplayError):
        parse_replay(session, dem(tmp_path), parser_returning(TRUNCATED), tmp_path / "raw")
    assert not (tmp_path / "raw").exists()
    assert session.get(Match, MATCH_ID).replay_state == "failed"


def test_unknown_match_is_refused(session, tmp_path):
    with pytest.raises(ReplayError, match="not stored"):
        parse_replay(session, dem(tmp_path, 123), parser_returning(LOG), tmp_path / "raw")
