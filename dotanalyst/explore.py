"""Explore, the front page of the tournament browser: what the poller keeps for it (Steam's live league games, OpenDota's
recent pro games, team logos) and the answer built from that, the catalog and the kept Liquipedia structures. Explore
itself never asks anyone: see Explore in IMPLEMENTATION.md."""
import json
import time
from pathlib import Path

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import catalog, liquipedia, steam
from .db import League, LeagueCatalog
from .opendota import pace

PRO_MATCHES = "https://api.opendota.com/api/proMatches"
RESULTS_SECONDS = 600  # OpenDota's recent pro games are asked at most this often
DONE_AFTER = 3 * 3600  # a series whose last game ended this long ago is over, whatever its score
SERIES_GAP = 6 * 3600  # games without a series id: the same teams' games this close together are one series
BEST_OF = {0: 1, 1: 3, 2: 5}  # series_type
LOGOS_PER_ROUND = 10  # new Steam logo lookups one live round may make


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


def live_logos(client: httpx.Client, key: str, games: list[dict], data: Path) -> None:
    """The logos of the live games' teams, up to LOGOS_PER_ROUND not asked before (steam.team_logo keeps every answer),
    noted in team_logos.json."""
    asked = set(_read(data / "logos.json") or {})
    teams, new = [], 0
    for g in games:
        for s in ("radiant", "dire"):
            team, ugc = g[s], g[s].get("logo_ugc")
            if not team["team_id"] or not ugc:
                continue
            if str(ugc) not in asked:
                if new >= LOGOS_PER_ROUND:
                    continue
                new += 1
                asked.add(str(ugc))
            teams.append({"team_id": team["team_id"], "name": team["name"], "logo": steam.team_logo(client, key, ugc, data)})
    remember_logos(data, teams)


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


# ---- which tournaments Explore follows, and its answer
SOON_DAYS = 14  # starting soon: a Liquipedia start date this many days ahead at most
FINISHED_DAYS = 30  # recently finished: an end date this many days back at most
CALENDAR_BACK, CALENDAR_AHEAD = 14, 42  # days the calendar shows around today
UPCOMING_HOURS = 24
SHOWN = 20  # upcoming matches and results at most
NEWCOMERS = 50  # the newest pro leagues without a game that are looked up on Liquipedia


def _start(r: LeagueCatalog) -> int | None:
    end = catalog.day_end(r.start_date)
    return end - 86399 if end else r.first_game


def ended(r: LeagueCatalog, now: float) -> bool:
    """Over by Liquipedia's end date. A league counts as active 30 days after its last game (catalog.status), so the
    end date is what tells a finished tournament from one with a few days off."""
    end = catalog.day_end(r.end_date)
    return end is not None and end < now


def tournaments(session: Session, now: float) -> list[LeagueCatalog]:
    """The tournaments whose Liquipedia structure Explore keeps: tier 1 to 3 with a page, live or active, starting
    within SOON_DAYS or ended within FINISHED_DAYS. Live first, then by tier and prize pool."""
    found = []
    for r in session.scalars(select(LeagueCatalog).where(LeagueCatalog.lp_page.is_not(None), LeagueCatalog.lp_tier.between(1, 3))):
        start, end = _start(r), catalog.day_end(r.end_date)
        recent = ended(r, now) and end >= now - FINISHED_DAYS * 86400
        soon = start is not None and now <= start <= now + SOON_DAYS * 86400
        playing = catalog.status(r, now) in ("live", "active") and not ended(r, now)
        if recent or soon or playing:
            found.append(r)
    return sorted(found, key=lambda r: (catalog.status(r, now) != "live", r.lp_tier, -(r.prize_usd or 0), -r.league_id))


def newcomers(session: Session, n: int = NEWCOMERS) -> list[int]:
    """The n newest leagues OpenDota lists as premium or professional with no game yet, never asked of Liquipedia:
    a tournament before its first game, which Explore's Starting soon needs a start date for."""
    query = select(LeagueCatalog.league_id).where(
        LeagueCatalog.tier.in_(("premium", "professional")), or_(LeagueCatalog.games.is_(None), LeagueCatalog.games == 0),
        LeagueCatalog.lp_checked.is_(None),
    ).order_by(LeagueCatalog.league_id.desc()).limit(n)  # fmt: skip
    return list(session.scalars(query))


def missing_region(session: Session) -> list[int]:
    """Leagues with a Liquipedia page asked before regions were read (region None; "" is asked, none said)."""
    query = select(LeagueCatalog.league_id).where(LeagueCatalog.lp_page.is_not(None), LeagueCatalog.region.is_(None))
    return list(session.scalars(query.order_by(LeagueCatalog.league_id.desc())))


def answer(session: Session, data: Path, now: float | None = None) -> dict:
    """GET /api/explore, from what is kept only: every section and the leagues they name (with region and whether
    online), for the browser to filter."""
    now = now or time.time()
    subscribed = set(session.scalars(select(League.league_id)))
    rows: dict[int, LeagueCatalog] = {}

    def league(league_id) -> LeagueCatalog | None:
        if league_id not in rows and (r := session.get(LeagueCatalog, league_id)) is not None:
            rows[league_id] = r
        return rows.get(league_id)

    known = logos(data)
    by_name = {(v.get("name") or "").lower(): (int(k), v["logo"]) for k, v in known.items() if v.get("name")}
    rank = lambda r: (r.lp_tier or 99, -(r.prize_usd or 0)) if r else (99, 0)  # noqa: E731

    kept_live = _read(data / "explore" / "live.json")
    live = []
    if kept_live and now - kept_live.get("read", 0) <= catalog.LIVE_MINUTES * 60:
        for g in kept_live.get("games", []):
            for s in ("radiant", "dire"):
                g[s]["logo"] = (known.get(str(g[s]["team_id"])) or {}).get("logo")
            live.append(g)
        live.sort(key=lambda g: (*rank(league(g["league_id"])), -(g["duration"] or 0)))

    followed = tournaments(session, now)
    upcoming = []
    for r in followed:
        for m in (liquipedia.kept(r.league_id, data) or {}).get("upcoming", []):
            names = [o["name"] if isinstance(o, dict) else o for o in m["opponents"]]
            if None in names or not (now <= (m.get("time") or 0) <= now + UPCOMING_HOURS * 3600):
                continue
            teams = [by_name.get(n.lower(), (0, None)) for n in names]
            upcoming.append({**m, "league_id": r.league_id,
                             "opponents": [{"name": n, "team_id": t, "logo": logo} for n, (t, logo) in zip(names, teams)]})  # fmt: skip
    upcoming = sorted(upcoming, key=lambda m: m["time"])[:SHOWN]

    results = series_of((_read(data / "explore" / "results.json") or {}).get("games", []), now)[:SHOWN]
    for s in results:
        for o in s["opponents"]:
            o["logo"] = (known.get(str(o["team_id"])) or {}).get("logo")

    every = list(session.scalars(select(LeagueCatalog).where(or_(
        LeagueCatalog.start_date.is_not(None), LeagueCatalog.end_date.is_not(None), LeagueCatalog.first_game.is_not(None)))))  # fmt: skip
    soon = sorted((r for r in every if (s := _start(r)) and catalog.day_end(r.start_date) and now <= s <= now + SOON_DAYS * 86400),
                  key=_start)  # fmt: skip
    calendar = []
    for r in every:
        if not r.lp_tier or not 1 <= r.lp_tier <= 3 or (start := _start(r)) is None:
            continue
        end = catalog.day_end(r.end_date) or (r.last_game if catalog.status(r, now) == "finished" else None)
        if start > now + CALENDAR_AHEAD * 86400 or (end or now) < now - CALENDAR_BACK * 86400:
            continue
        calendar.append({"league_id": r.league_id, "start": start, "end": end or max(now, start), "open": end is None})
        league(r.league_id)
    finished = []
    for r in sorted((r for r in followed if ended(r, now)), key=lambda r: -(catalog.day_end(r.end_date) or 0)):
        name = (liquipedia.kept(r.league_id, data) or {}).get("winner")
        finished.append({"league_id": r.league_id,
                         "winner": {"name": name, "logo": by_name.get(name.lower(), (0, None))[1]} if name else None})  # fmt: skip
    big = [r["league_id"] for r in catalog.explore(session, now)["big"]]

    for league_id in [g["league_id"] for g in live] + [m["league_id"] for m in upcoming] + [s["league_id"] for s in results] \
            + [r.league_id for r in soon] + [f["league_id"] for f in finished] + big:  # fmt: skip
        league(league_id)
    leagues = {str(i): {**catalog.row(r, now, subscribed), "online": (r.location or "").startswith("Online")} for i, r in rows.items()}
    return {
        "leagues": leagues, "live": live, "upcoming": upcoming, "results": results, "soon": [r.league_id for r in soon],
        "calendar": calendar, "big": big, "finished": finished,
    }  # fmt: skip
