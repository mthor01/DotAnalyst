"""Explore, the front page of the tournament browser: what the poller keeps for it (Steam's live league games, OpenDota's
recent pro games, team logos) and the answer built from that, the catalog and the kept Liquipedia structures. Explore
itself never asks anyone: see Explore in IMPLEMENTATION.md."""
import json
from pathlib import Path

import httpx

from .opendota import pace

PRO_MATCHES = "https://api.opendota.com/api/proMatches"
RESULTS_SECONDS = 600  # OpenDota's recent pro games are asked at most this often
DONE_AFTER = 3 * 3600  # a series whose last game ended this long ago is over, whatever its score
SERIES_GAP = 6 * 3600  # games without a series id: the same teams' games this close together are one series
BEST_OF = {0: 1, 1: 3, 2: 5}  # series_type


def _read(path: Path) -> dict | None:
    try:
        found = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def _write(path: Path, found: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(found))


def parse_live(games: list[dict]) -> list[dict]:
    """Steam's live league games: league, teams with their Steam logo id, series score, and the clock and kills when
    Steam sends them."""
    found = []
    for g in games:
        board = g.get("scoreboard") or {}

        def team(s: str) -> dict:
            t = g.get(f"{s}_team") or {}
            return {"team_id": t.get("team_id") or 0, "name": t.get("team_name") or None, "logo_ugc": t.get("team_logo") or None}

        found.append({
            "league_id": g.get("league_id"), "match_id": g.get("match_id"), "radiant": team("radiant"), "dire": team("dire"),
            "series": [g.get("radiant_series_wins") or 0, g.get("dire_series_wins") or 0],
            "best_of": BEST_OF.get(g.get("series_type") or 0, 1), "duration": board.get("duration"),
            "score": [(board.get("radiant") or {}).get("score"), (board.get("dire") or {}).get("score")],
        })  # fmt: skip
    return found


def keep_live(games: list[dict], data: Path, now: float) -> None:
    """Keep the live games of one look at Steam in data/explore/live.json."""
    _write(data / "explore" / "live.json", {"read": now, "games": parse_live(games)})


def logos(data: Path) -> dict[str, dict]:
    """Every team logo known: team id (as text) to its name and logo address, data/team_logos.json."""
    return _read(data / "team_logos.json") or {}


def remember_logos(data: Path, teams: list[dict]) -> None:
    """Note the logos of these teams (team_id, name, logo); a team without an id or a logo is left out."""
    known = logos(data)
    new = {str(t["team_id"]): {"name": t.get("name"), "logo": t["logo"]} for t in teams if t.get("team_id") and t.get("logo")}
    if any(known.get(k) != v for k, v in new.items()):
        _write(data / "team_logos.json", known | new)


def fetch_results(client: httpx.Client, data: Path, now: float) -> int:
    """OpenDota's last 100 pro games into data/explore/results.json, unless read under RESULTS_SECONDS ago. A failed
    request keeps the old ones. Returns the games read."""
    stored = data / "explore" / "results.json"
    kept = _read(stored)
    if kept and now - kept.get("read", 0) < RESULTS_SECONDS:
        return 0
    pace()
    try:
        response = client.get(PRO_MATCHES, timeout=30)
        games = response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        games = None
    if not isinstance(games, list):
        return 0
    _write(stored, {"read": now, "games": games})
    return len(games)


def series_of(games: list[dict], now: float) -> list[dict]:
    """OpenDota's pro games as finished series, newest end first, each shaped like a Liquipedia match (the series
    window reads it). One series: the same series id; without one, the same league and teams within SERIES_GAP, a Bo1
    alone. Finished: a team won more than half its Bo, or its last game ended over DONE_AFTER ago."""
    groups: list[list[dict]] = []
    open_: dict = {}  # key -> its group, for games without a series id
    for g in sorted(games, key=lambda g: g.get("start_time") or 0):
        teams = tuple(sorted(str(g.get(f"{s}_team_id") or g.get(f"{s}_name") or "") for s in ("radiant", "dire")))
        if g.get("series_id"):
            key = ("id", g["series_id"])
        elif (g.get("series_type") or 0) and all(teams):
            key = ("teams", g.get("leagueid"), teams)
        else:
            key = ("game", g.get("match_id"))
        group = open_.get(key)
        if group is None or (key[0] == "teams" and g["start_time"] - group[-1]["start_time"] > SERIES_GAP):
            group = open_[key] = []
            groups.append(group)
        group.append(g)
    found = []
    for group in groups:
        first = group[0]
        opponents = [{"name": first.get(f"{s}_name"), "team_id": first.get(f"{s}_team_id") or 0} for s in ("radiant", "dire")]
        maps = []
        for g in group:
            same = (g.get("radiant_team_id") or 0) == opponents[0]["team_id"] if opponents[0]["team_id"] else g.get("radiant_name") == opponents[0]["name"]
            won = g.get("radiant_win")
            maps.append({"team1side": "radiant" if same else "dire", "match_id": g["match_id"],
                         "winner": None if won is None else 0 if won == same else 1})  # fmt: skip
        best_of = BEST_OF.get(max(g.get("series_type") or 0 for g in group), 1)
        score = [sum(m["winner"] == i for m in maps) for i in (0, 1)]
        end = max((g.get("start_time") or 0) + (g.get("duration") or 0) for g in group)
        if max(score) > best_of / 2:
            winner = 0 if score[0] > score[1] else 1
        elif now - end > DONE_AFTER:
            winner = None if score[0] == score[1] else 0 if score[0] > score[1] else 1
        else:
            continue  # still being played
        found.append({
            "opponents": opponents, "time": end, "match_ids": [m["match_id"] for m in maps], "maps": maps, "score": score,
            "winner": winner, "best_of": best_of, "league_id": first.get("leagueid"), "league_name": first.get("league_name"),
        })  # fmt: skip
    return sorted(found, key=lambda s: -s["time"])
