import bz2
import gzip
import json
import time
from compression import zstd
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from .db import DATA, Match

PARSER_URL = "http://localhost:5600/"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
OPENDOTA_MATCH = "https://api.opendota.com/api/matches/{}"
RETRY_DAYS = 14  # a match this old with no replay to get is given up on


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


def replay_url(match_id: int, cluster: int, salt: int) -> str:
    return f"http://replay{cluster}.valve.net/570/{match_id}_{salt}.dem.bz2"


def replay_salt(match_id: int, client: httpx.Client, opendota_dir: Path) -> int | None:
    """Replay salt from OpenDota, or None if it has none. A response with a salt is kept and never asked for again."""
    stored = opendota_dir / f"{match_id}.json.gz"
    if stored.exists():
        return json.loads(gzip.decompress(stored.read_bytes()))["replay_salt"]
    response = client.get(OPENDOTA_MATCH.format(match_id), timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    try:
        salt = response.json()["replay_salt"]
    except (ValueError, KeyError, TypeError):
        return None
    if type(salt) is not int:  # it goes into a URL, so nothing but a number passes
        return None
    opendota_dir.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(gzip.compress(response.content))
    return salt


def download_replay(url: str, dem: Path, client: httpx.Client) -> bool:
    """Download a .dem.bz2 and write it decompressed. False when Valve does not have the file."""
    decompressor = None
    with client.stream("GET", url, timeout=60) as response:
        if response.status_code == 404:
            return False
        response.raise_for_status()
        dem.parent.mkdir(parents=True, exist_ok=True)
        with dem.open("wb") as out:
            for chunk in response.iter_bytes():
                # the name says bz2, but in 2026 Valve sends Zstandard; the first bytes tell which
                decompressor = decompressor or (
                    zstd.ZstdDecompressor() if chunk.startswith(ZSTD_MAGIC) else bz2.BZ2Decompressor()
                )
                try:
                    content = decompressor.decompress(chunk)
                except (OSError, EOFError, zstd.ZstdError) as error:
                    raise ReplayError(f"{dem.name}: download is not a valid archive") from error
                out.write(content)
    if decompressor is None or not decompressor.eof:
        raise ReplayError(f"{dem.name}: download ended early")
    return True


def fetch_replay(session: Session, match: Match, client: httpx.Client, data: Path = DATA) -> bool:
    """Download and parse one match's replay. False when there is no replay to get (yet)."""
    # recorded before any request, so a match that keeps erroring waits an hour like any other
    match.replay_state = "pending"
    match.replay_tried_at = int(time.time())
    session.commit()
    dem = data / "tmp" / f"{match.match_id}.dem"
    try:
        salt = replay_salt(match.match_id, client, data / "opendota")
        if salt is None or not download_replay(replay_url(match.match_id, match.cluster, salt), dem, client):
            if time.time() - match.start_time > RETRY_DAYS * 86400:
                match.replay_state = "unavailable"
                session.commit()
            return False
        parse_replay(session, dem, client, data / "raw")
        return True
    finally:
        dem.unlink(missing_ok=True)
