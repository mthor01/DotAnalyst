"""Pre-commit check: refuses staged files that hold the account id or Steam id of a real player.

The real ids are every account the local database has seen (tracked accounts, everyone in a stored match or league
game), so a fixture saved from a live answer is caught. Made-up ids in fixtures are small numbers (1001, 2001, ...).
"""

import gzip
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

DB = Path("data/dotanalyst.db")
STEAM64 = 76561197960265728  # a Steam id is the account id plus this
ANONYMOUS = 4294967295

if not DB.exists():
    sys.exit(0)  # shortcut: without a local database there is nothing to compare with
db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
ids = {row[0] for row in db.execute("SELECT account_id FROM accounts UNION SELECT account_id FROM match_players")}
ids |= {
    row[0]
    for row in db.execute("SELECT json_extract(p.value, '$.account_id') FROM league_matches, json_each(raw_json, '$.players') p")
}
ids -= {None, ANONYMOUS}
ids |= {i + STEAM64 for i in ids}

staged = subprocess.run(
    ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], capture_output=True, check=True
).stdout.decode()
found = []
for name in filter(None, staged.split("\0")):
    blob = subprocess.run(["git", "show", f":{name}"], capture_output=True, check=True).stdout
    if name.endswith(".gz"):
        blob = gzip.decompress(blob)
    hits = {int(n) for n in re.findall(rb"(?<!\d)\d{6,17}(?!\d)", blob)} & ids
    if hits:
        found.append(f"  {name}: {', '.join(map(str, sorted(hits)[:5]))}{' ...' if len(hits) > 5 else ''}")
if found:
    print("Commit refused: these staged files hold ids of real players (replace them with made-up ones):", file=sys.stderr)
    print("\n".join(found), file=sys.stderr)
    sys.exit(1)
