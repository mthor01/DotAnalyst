"""The tournament page of any league: its catalog row, teams, series and games. A subscribed league shows its stored
games; any other a preview, from OpenDota for a pro league and from Steam for an amateur one, kept in
data/leagues/<id>.json. Preview games never go into league_matches: there they would join the team pages and have
their replays fetched. See Tournament browser in IMPLEMENTATION.md."""
import json
import time
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import catalog, liquipedia, steam
from .db import DATA, League, LeagueCatalog, LeagueMatch
from .opendota import pace

OPENDOTA = "https://api.opendota.com/api/leagues/{}/{}"
PREVIEW_HOURS = 6  # a league still playing is fetched again after this; a finished one never
HISTORY_PAGES = 5  # Steam lists 100 games a page and at most 500 of a league
STEAM_DETAILS = 20  # the newest games of an amateur preview whose details (teams' names, result) are asked for
BEST_OF = {0: 1, 1: 3, 2: 5}  # series_type


def side(team_id, name) -> dict:
    return {"team_id": team_id or 0, "name": name or None}


def from_opendota(m: dict) -> dict:
    """One game as the page shows it, from OpenDota's league games."""
    return {
        "match_id": m["match_id"], "start_time": m["start_time"], "series_id": m.get("series_id") or None,
        "series_type": m.get("series_type") or 0,
        "radiant": side(m.get("radiant_team_id"), m.get("radiant_team_name")),
        "dire": side(m.get("dire_team_id"), m.get("dire_team_name")),
        "radiant_win": m.get("radiant_win"), "radiant_score": m.get("radiant_score"), "dire_score": m.get("dire_score"),
    }  # fmt: skip


def from_steam(entry: dict, found: dict | None) -> dict:
    """One game of Steam's league history, with its details when they were asked for (else no names, no result)."""
    d = found or {}
    return {
        "match_id": entry["match_id"], "start_time": entry["start_time"], "series_id": entry.get("series_id") or None,
        "series_type": entry.get("series_type") or 0,
        "radiant": side(entry.get("radiant_team_id"), d.get("radiant_name")),
        "dire": side(entry.get("dire_team_id"), d.get("dire_name")),
        "radiant_win": d.get("radiant_win"), "radiant_score": d.get("radiant_score"), "dire_score": d.get("dire_score"),
    }  # fmt: skip


def from_stored(m: LeagueMatch, series_of: dict) -> dict:
    series_id, series_type = series_of.get(str(m.match_id), (None, 0))
    return {
        "match_id": m.match_id, "start_time": m.start_time, "series_id": series_id, "series_type": series_type,
        "radiant": side(m.radiant_team_id, m.radiant_name), "dire": side(m.dire_team_id, m.dire_name),
        "radiant_win": m.radiant_win, "radiant_score": m.raw_json.get("radiant_score"),
        "dire_score": m.raw_json.get("dire_score"),
    }  # fmt: skip


def series(games: list[dict]) -> list[dict]:
    """The games grouped by series, newest first. The first team is the first game's Radiant; a game without a series
    id is a series of its own; the score counts the games with a known winner."""
    grouped: dict = {}
    for g in sorted(games, key=lambda g: g["start_time"]):
        s = grouped.setdefault(g["series_id"] or f"game {g['match_id']}", {
            "series_id": g["series_id"], "best_of": BEST_OF.get(g["series_type"], 1), "teams": [g["radiant"], g["dire"]],
            "score": [0, 0], "start_time": g["start_time"], "last_time": g["start_time"], "games": 0,
        })  # fmt: skip
        s["games"] += 1
        s["last_time"] = g["start_time"]
        if g["radiant_win"] is not None:
            winner = (g["radiant"] if g["radiant_win"] else g["dire"])["team_id"]
            s["score"][0 if winner == s["teams"][0]["team_id"] else 1] += 1
    return sorted(grouped.values(), key=lambda s: -s["start_time"])


def teams(games: list[dict], known: list[dict]) -> list[dict]:
    """Every team of the games with its game and series record; OpenDota's teams add rating and logo. Most games first."""
    found: dict[int, dict] = {}
    for t in known:
        found[t["team_id"]] = {"team_id": t["team_id"], "name": t.get("name"), "logo": t.get("logo_url"),
                               "rating": t.get("rating"), "games": 0, "wins": 0, "series": 0, "series_wins": 0}  # fmt: skip
    for g in sorted(games, key=lambda g: g["start_time"]):
        for s in ("radiant", "dire"):
            team = g[s]
            if not team["team_id"]:
                continue
            t = found.setdefault(team["team_id"], {"team_id": team["team_id"], "name": None, "logo": None,
                                                    "rating": None, "games": 0, "wins": 0, "series": 0, "series_wins": 0})  # fmt: skip
            t["name"] = team["name"] or t["name"]
            t["games"] += 1
            t["wins"] += g["radiant_win"] is not None and g["radiant_win"] == (s == "radiant")
    for s in series(games):
        a, b = s["score"]
        for i, team in enumerate(s["teams"]):
            if team["team_id"] in found:
                found[team["team_id"]]["series"] += 1
                found[team["team_id"]]["series_wins"] += (a, b)[i] > (b, a)[i]
    return sorted((t for t in found.values() if t["games"]), key=lambda t: (-t["games"], (t["name"] or "").lower()))


def _opendota(client: httpx.Client, league_id: int, what: str) -> list:
    pace()
    try:
        response = client.get(OPENDOTA.format(league_id, what), timeout=30)
        body = response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        body = None
    return body if isinstance(body, list) else []


def steam_history(client: httpx.Client, key: str, league_id: int) -> list[dict]:
    """Steam's list of the league's games, newest first: up to HISTORY_PAGES pages."""
    listed: list[dict] = []
    params: dict = {"league_id": league_id}
    for _ in range(HISTORY_PAGES):
        page = steam.call(client, key, steam.HISTORY, **params).get("matches", [])
        if not page:
            break
        listed += page
        params["start_at_match_id"] = page[-1]["match_id"] - 1
    return listed


def fetch(client: httpx.Client, key: str, league_id: int, subscribed: bool) -> dict:
    """A new preview. A subscribed league needs only Steam's list, for the series of its stored games."""
    if not subscribed:
        games = _opendota(client, league_id, "matches")
        if games:
            return {"source": "opendota", "games": [from_opendota(m) for m in games],
                    "teams": _opendota(client, league_id, "teams")}  # fmt: skip
    if not key:
        return {"source": "none", "games": [], "teams": []}
    try:
        listed = steam_history(client, key, league_id)
    except steam.SteamError:
        return {"source": "none", "games": [], "teams": []}
    if subscribed:
        return {"source": "steam", "series_of": {str(e["match_id"]): [e.get("series_id") or None, e.get("series_type") or 0] for e in listed}}
    newest = sorted(listed, key=lambda e: -e["start_time"])
    games = []
    for i, entry in enumerate(newest):
        found = None
        if i < STEAM_DETAILS:
            try:
                found = steam.details(client, key, entry)
            except steam.SteamError:
                pass
        games.append(from_steam(entry, found))
    return {"source": "steam", "games": games, "teams": []}


def page(session: Session, client: httpx.Client, key: str, league_id: int, data: Path = DATA, now: float | None = None) -> dict:
    now = now or time.time()
    row = session.get(LeagueCatalog, league_id)
    if row is None:  # a league id typed by hand that no list has
        row = LeagueCatalog(league_id=league_id, name=f"League {league_id}")
        session.add(row)
        session.commit()
    if liquipedia.due(row, now):
        liquipedia.lookup(session, client, league_id, now)
    subscribed = session.get(League, league_id) is not None
    stored = data / "leagues" / f"{league_id}.json"
    cached = json.loads(stored.read_text()) if stored.exists() else None
    fresh = cached is not None and cached.get("subscribed") == subscribed and (
        now - cached["fetched"] < PREVIEW_HOURS * 3600 or catalog.status(row, now) == "finished")
    if not fresh:
        cached = {**fetch(client, key, league_id, subscribed), "fetched": now, "subscribed": subscribed}
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_text(json.dumps(cached))
    if subscribed:
        rows = session.scalars(select(LeagueMatch).where(LeagueMatch.league_id == league_id))
        games, source = [from_stored(m, cached.get("series_of", {})) for m in rows], "stored"
    else:
        games, source = cached["games"], cached["source"]
    games = sorted(games, key=lambda g: -g["start_time"])
    if games:  # what the page knows is the best count there is for a league OpenDota's explorer has not
        row.games, row.first_game, row.last_game = len(games), games[-1]["start_time"], games[0]["start_time"]
        session.commit()
    return {
        "league": catalog.row(row, now, {league_id} if subscribed else set()), "source": source, "subscribed": subscribed,
        "teams": teams(games, cached.get("teams", [])), "series": series(games), "games": games,
    }  # fmt: skip
