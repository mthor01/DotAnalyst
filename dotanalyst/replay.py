import gzip
import json
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from .db import DATA, Match

PARSER_URL = "http://localhost:5600/"


class ReplayError(Exception):
    pass


def epilogue_match_id(log: bytes) -> int | None:
    """Match id from the epilogue line, or None if the parse did not complete."""
    for line in reversed(log.splitlines()):
        if b"epilogue" not in line:
            continue
        try:
            event = json.loads(line)
            if event["type"] == "epilogue":
                return json.loads(event["key"])["gameInfo_"]["dota_"]["matchId_"]
        except (ValueError, KeyError, TypeError):
            continue
    return None


def parse_replay(
    session: Session, dem: Path, client: httpx.Client, raw_dir: Path = DATA / "raw"
) -> Path:
    """Send a .dem to the parser and store its event log. Never re-parses a stored match."""
    if not dem.stem.isdigit():
        raise ReplayError(f"{dem.name}: file name must be <match_id>.dem")
    match_id = int(dem.stem)
    match = session.get(Match, match_id)
    if match is None:
        raise ReplayError(f"match {match_id} is not stored; run sync first")
    out = raw_dir / f"{match_id}.jsonl.gz"
    if match.replay_state == "parsed" and out.exists():
        return out

    # shortcut: whole replay held in memory (up to ~250 MB), stream it if that ever hurts
    response = client.post(PARSER_URL, content=dem.read_bytes(), timeout=600)
    # the parser answers 200 even when it crashed, so only the epilogue proves completeness
    if epilogue_match_id(response.content) != match_id:
        match.replay_state = "failed"
        session.commit()
        raise ReplayError(f"match {match_id}: parser output is incomplete or for another match")

    raw_dir.mkdir(parents=True, exist_ok=True)
    out.write_bytes(gzip.compress(response.content))
    match.replay_state = "parsed"
    session.commit()
    return out
