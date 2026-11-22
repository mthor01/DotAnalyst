"""Checks the bundled parser (build/parser) end to end: starts it, parses one replay, checks the replay's epilogue.
uv run python packaging/smoke_parser.py [<match_id>.dem]. Without a file it takes a recent pro match's replay from
OpenDota, which is what the release workflow does before it publishes a parser. Exits with NO_REPLAY when OpenDota
gives no replay: that says nothing about the parser, so the release workflow publishes anyway, with a warning."""
import bz2
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotanalyst import parser  # noqa: E402
from dotanalyst.replay import PARSER_URL, epilogue_match_id  # noqa: E402

NO_REPLAY = 2


def pro_replay(client: httpx.Client) -> tuple[int, bytes] | None:
    try:
        # the newest have no replay yet, so look a little further back
        for match in client.get("https://api.opendota.com/api/proMatches").raise_for_status().json()[5:15]:
            url = client.get(f"https://api.opendota.com/api/matches/{match['match_id']}").json().get("replay_url")
            replay = url and client.get(url, timeout=300)
            if replay and replay.status_code == 200:
                return match["match_id"], bz2.decompress(replay.content)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError) as error:  # down, an error page, a cut-off replay
        print(f"OpenDota: {error!r}")
    return None


with httpx.Client(follow_redirects=True, timeout=30) as client:
    if len(sys.argv) > 1:
        dem = Path(sys.argv[1])
        match_id, replay = int(dem.stem), dem.read_bytes()
    elif found := pro_replay(client):
        match_id, replay = found
    else:
        print("no recent pro replay to check the parser with")
        sys.exit(NO_REPLAY)
    if parser.answers():
        sys.exit("a parser answers on port 5600 already: stop it, so that the bundled one is the one checked")
    process = parser.start()
    try:
        if process is None or process.poll() is not None:
            sys.exit(f"the bundled parser did not start, see {parser.DATA / 'parser.log'}")
        found = epilogue_match_id(client.post(PARSER_URL, content=replay, timeout=600).content)
    finally:
        parser.stop(process)
if found not in (0, match_id):  # Valve leaves the id at 0 in some replays
    sys.exit(f"the parser's output for match {match_id} has {'no epilogue' if found is None else f'match {found}'}")
print(f"parser ok: match {match_id} parsed")
