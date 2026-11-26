"""Tournament stats from stored league games (`LeagueMatch.raw_json`): heroes picked and banned, players, standings
and head-to-head. Computed per request; see the Tournament sections of IMPLEMENTATION.md."""
from collections import Counter, defaultdict

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .db import League, LeagueMatch
from .steam import ANONYMOUS

SERIES_GAP = 6 * 3600  # head-to-head: games of one league closer than this are one series (stored rows have no series id)


def heroes(rows: list[LeagueMatch]) -> list[dict]:
    """Picks, wins and bans per hero; contested = (picks + bans) / the games with a draft. Most contested first."""
    found: dict[int, dict] = {}
    drafted = 0
    for m in rows:
        draft = m.raw_json.get("picks_bans")
        if not draft:  # an all-pick lobby has none
            continue
        drafted += 1
        for p in draft:
            h = found.setdefault(p["hero_id"], {"hero_id": p["hero_id"], "picks": 0, "wins": 0, "bans": 0})
            if p["is_pick"]:
                h["picks"] += 1
                h["wins"] += m.radiant_win == (p["team"] == 0)
            else:
                h["bans"] += 1
    for h in found.values():
        h["contested"] = round((h["picks"] + h["bans"]) / drafted, 4)
    return sorted(found.values(), key=lambda h: (-h["contested"], -h["picks"], h["hero_id"]))


def players(rows: list[LeagueMatch], names: dict[int, tuple[str | None, str | None]]) -> list[dict]:
    """Per player (anonymous left out): games, wins, per-game averages, KDA on totals, the team it played most for and
    its three most played heroes. Most games first."""
    totals: dict[int, Counter] = defaultdict(Counter)
    teams: dict[int, Counter] = defaultdict(Counter)
    played: dict[int, Counter] = defaultdict(Counter)
    for m in rows:
        for p in m.raw_json.get("players", []):
            account_id = p.get("account_id")
            if account_id in (None, ANONYMOUS):
                continue
            radiant = p["player_slot"] < 128
            t = totals[account_id]
            t["games"] += 1
            t["wins"] += m.radiant_win == radiant
            for k in ("kills", "deaths", "assists", "gold_per_min", "xp_per_min", "last_hits", "hero_damage"):
                t[k] += p.get(k) or 0
            teams[account_id][m.radiant_team_id if radiant else m.dire_team_id] += 1
            played[account_id][p["hero_id"]] += 1
    found = []
    for account_id, t in totals.items():
        n = t["games"]
        name, avatar = names.get(account_id, (None, None))
        found.append({
            "account_id": account_id, "name": name, "avatar": avatar, "team_id": teams[account_id].most_common(1)[0][0] or 0,
            "games": n, "wins": t["wins"], "kills": round(t["kills"] / n, 1), "deaths": round(t["deaths"] / n, 1),
            "assists": round(t["assists"] / n, 1), "kda": round((t["kills"] + t["assists"]) / max(t["deaths"], 1), 2),
            "gpm": round(t["gold_per_min"] / n, 1), "xpm": round(t["xp_per_min"] / n, 1),
            "last_hits": round(t["last_hits"] / n, 1), "hero_damage": round(t["hero_damage"] / n, 1),
            "heroes": [h for h, _ in played[account_id].most_common(3)],
        })  # fmt: skip
    return sorted(found, key=lambda p: (-p["games"], p["account_id"]))


def standings(series: list[dict]) -> list[dict]:
    """A table from series results (league_page.series): series, then maps, then map difference. Unplayed series
    (no game with a known result) do not count."""
    found: dict[int, dict] = {}
    for s in series:
        score = s["score"]
        if not sum(score):
            continue
        for i, team in enumerate(s["teams"]):
            if not team["team_id"]:
                continue
            t = found.setdefault(team["team_id"], {"team_id": team["team_id"], "name": team["name"], "series_wins": 0,
                                                   "series_losses": 0, "map_wins": 0, "map_losses": 0})  # fmt: skip
            t["name"] = t["name"] or team["name"]
            mine, theirs = score[i], score[1 - i]
            t["series_wins"] += mine > theirs
            t["series_losses"] += mine < theirs
            t["map_wins"] += mine
            t["map_losses"] += theirs
    return sorted(found.values(), key=lambda t: (-t["series_wins"], t["series_losses"], t["map_losses"] - t["map_wins"],
                                                 (t["name"] or "").lower()))  # fmt: skip


def head_to_head(session: Session, a: int, b: int) -> dict:
    """Every stored league game between the two teams, of any league: games won by each and their series, newest
    first. A series is the games of one league with less than SERIES_GAP between consecutive ones."""
    m = LeagueMatch
    rows = session.scalars(
        select(m)
        .where(or_(and_(m.radiant_team_id == a, m.dire_team_id == b), and_(m.radiant_team_id == b, m.dire_team_id == a)))
        .order_by(m.league_id, m.start_time)
    ).all()
    names = {r.league_id: r.name for r in session.execute(select(League.league_id, League.name))}
    sides: dict[int, str | None] = {a: None, b: None}
    wins, series, last = [0, 0], [], None
    for g in rows:
        sides[g.radiant_team_id] = g.radiant_name or sides[g.radiant_team_id]
        sides[g.dire_team_id] = g.dire_name or sides[g.dire_team_id]
        if last is None or g.league_id != last.league_id or g.start_time - last.start_time >= SERIES_GAP:
            series.append({"league_id": g.league_id, "league_name": names.get(g.league_id), "start_time": g.start_time,
                           "score": [0, 0]})  # fmt: skip
        last = g
        if g.radiant_win is None:
            continue
        winner = g.radiant_team_id if g.radiant_win else g.dire_team_id
        i = 0 if winner == a else 1
        wins[i] += 1
        series[-1]["score"][i] += 1
    return {
        "teams": [{"team_id": a, "name": sides[a]}, {"team_id": b, "name": sides[b]}], "games": len(rows), "wins": wins,
        "series": sorted(series, key=lambda s: -s["start_time"]),
    }  # fmt: skip


def played_rosters(rows: list[LeagueMatch], names: dict[int, tuple[str | None, str | None]]) -> dict[int, list[dict]]:
    """Per team, the players seen playing for it in these games (anonymous left out), most games first."""
    counts: dict[int, Counter] = defaultdict(Counter)
    for m in rows:
        for p in m.raw_json.get("players", []):
            account_id = p.get("account_id")
            team_id = m.radiant_team_id if p["player_slot"] < 128 else m.dire_team_id
            if account_id not in (None, ANONYMOUS) and team_id:
                counts[team_id][account_id] += 1
    return {
        team_id: [{"account_id": a, "name": names.get(a, (None, None))[0], "avatar": names.get(a, (None, None))[1],
                   "games": n} for a, n in sorted(c.items(), key=lambda x: (-x[1], x[0]))]  # fmt: skip
        for team_id, c in counts.items()
    }


def logo_ids(rows: list[LeagueMatch]) -> dict[int, int]:
    """Per team, the UGC id of its logo in its newest game that has one."""
    found: dict[int, int] = {}
    for m in sorted(rows, key=lambda m: -m.start_time):
        for team_id, logo in ((m.radiant_team_id, m.raw_json.get("radiant_logo")), (m.dire_team_id, m.raw_json.get("dire_logo"))):
            if team_id and logo and team_id not in found:
                found[team_id] = logo
    return found
