"""Aggregations over stored matches. Every query is seen from one tracked account's side, or from one league team's."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from .db import TABLES, Account, Lane, LeagueMatch, Match, MatchPlayer, Metric, PlayerName, Ward
from .steam import ANONYMOUS, LEAGUES, match_rows

OTHER = aliased(MatchPlayer)
IS_RADIANT = MatchPlayer.player_slot < 128
WON = case((IS_RADIANT == Match.radiant_win, 1), else_=0)
SAME_TEAM = (OTHER.player_slot < 128) == IS_RADIANT
SCOREBOARD = (
    "player_slot", "account_id", "hero_id", "kills", "deaths", "assists", "last_hits", "denies", "gold_per_min",
    "xp_per_min", "net_worth", "level", "hero_damage", "tower_damage", "hero_healing", "items",
)  # fmt: skip
AVERAGED = ("kills", "deaths", "assists", "last_hits", "gold_per_min", "xp_per_min")  # of a league player on a hero


def between(start_time, date_from: date | None, date_to: date | None) -> list:
    """Conditions on a start_time column for local days, both inclusive."""
    found = []
    if date_from is not None:
        found.append(start_time >= datetime.combine(date_from, time.min).timestamp())
    if date_to is not None:
        found.append(start_time < datetime.combine(date_to + timedelta(days=1), time.min).timestamp())
    return found


def conditions(
    account_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    game_mode: int | None = None,
    lobby_type: int | None = None,
    league_id: int | None = None,
) -> list:
    """SQL conditions for the filters every view shares. Dates are local days, both inclusive."""
    found = [MatchPlayer.account_id == account_id, *between(Match.start_time, date_from, date_to)]
    if league_id is not None:
        found.append(Match.match_id.in_(select(LeagueMatch.match_id).where(LeagueMatch.league_id == league_id)))
    if game_mode is not None:
        found.append(Match.game_mode == game_mode)
    if lobby_type is not None:
        found.append(Match.lobby_type == lobby_type)
    return found


def _mine(*columns):
    # select_from pins "my" row as the left side even when the first column comes from OTHER
    return select(*columns).select_from(MatchPlayer).join(Match, Match.match_id == MatchPlayer.match_id)


def _rows(session: Session, statement) -> list[dict]:
    return [dict(row._mapping) for row in session.execute(statement)]


def matches(session: Session, where: list) -> list[dict]:
    """The account's matches, newest first. `lane` and `lane_nw_diff` are None without a parsed replay."""
    p = MatchPlayer
    with_tracked = (
        select(OTHER.match_id)
        .join(Account, and_(Account.account_id == OTHER.account_id, Account.active))
        .where(OTHER.match_id == p.match_id, OTHER.account_id != p.account_id, SAME_TEAM)
        .exists()
    )
    return _rows(
        session,
        _mine(
            Match.match_id, Match.start_time, Match.duration, Match.game_mode, Match.lobby_type,
            Match.replay_state, WON.label("win"), p.hero_id, p.kills, p.deaths, p.assists,
            p.last_hits, p.denies, p.gold_per_min, p.xp_per_min, p.net_worth, p.items,
            IS_RADIANT.label("radiant"), Lane.lane, Metric.value.label("lane_nw_diff"),
            with_tracked.label("with_tracked"),
        )
        .outerjoin(Lane, and_(Lane.match_id == p.match_id, Lane.player_slot == p.player_slot))
        .outerjoin(
            Metric,
            and_(Metric.match_id == p.match_id, Metric.player_slot == p.player_slot, Metric.name == "lane_nw_diff"),
        )
        .where(*where)
        .order_by(Match.start_time.desc()),
    )


def heroes(session: Session, where: list) -> list[dict]:
    p = MatchPlayer
    games = func.count().label("games")
    return _rows(
        session,
        _mine(
            p.hero_id, games, func.sum(WON).label("wins"),
            func.avg(p.kills).label("kills"), func.avg(p.deaths).label("deaths"),
            func.avg(p.assists).label("assists"), func.avg(p.gold_per_min).label("gold_per_min"),
            func.avg(p.xp_per_min).label("xp_per_min"),
        )
        .where(*where)
        .group_by(p.hero_id)
        .order_by(games.desc(), p.hero_id),
    )


def teammates(session: Session, where: list) -> list[dict]:
    """Games and wins on the same team as each other tracked account."""
    games = func.count().label("games")
    return _rows(
        session,
        _mine(OTHER.account_id, Account.label, games, func.sum(WON).label("wins"))
        .join(
            OTHER,
            and_(OTHER.match_id == MatchPlayer.match_id, OTHER.account_id != MatchPlayer.account_id, SAME_TEAM),
        )
        .join(Account, and_(Account.account_id == OTHER.account_id, Account.active))
        .where(*where)
        .group_by(OTHER.account_id, Account.label)
        .order_by(games.desc()),
    )


def matchups(session: Session, where: list) -> list[dict]:
    """Per hero: games and wins with it on my team, and against it. Wins are always mine."""
    ally = SAME_TEAM.label("ally")
    rows = session.execute(
        _mine(OTHER.hero_id, ally, func.count().label("games"), func.sum(WON).label("wins"))
        .join(OTHER, and_(OTHER.match_id == MatchPlayer.match_id, OTHER.player_slot != MatchPlayer.player_slot))
        .where(*where)
        .group_by(OTHER.hero_id, ally)
    )
    result: dict[int, dict] = {}
    for hero_id, is_ally, games, wins in rows:
        entry = result.setdefault(
            hero_id, {"hero_id": hero_id, "with_games": 0, "with_wins": 0, "against_games": 0, "against_wins": 0}
        )
        side = "with" if is_ally else "against"
        entry[f"{side}_games"], entry[f"{side}_wins"] = games, wins
    return sorted(result.values(), key=lambda e: -(e["with_games"] + e["against_games"]))


def wards(session: Session, where: list) -> list[dict]:
    """Every ward the account placed in its parsed matches: the match, the kind, the place and the side played."""
    ward = and_(Ward.match_id == MatchPlayer.match_id, Ward.player_slot == MatchPlayer.player_slot)
    columns = (Match.match_id, Ward.type, Ward.x, Ward.y, IS_RADIANT.label("radiant"))
    return _rows(session, _mine(*columns).join(Ward, ward).where(*where))


def match(session: Session, match_id: int) -> dict | None:
    """One match: the scoreboard, plus the replay stats where there are any (empty lists otherwise).

    A league game is in `matches` only once its replay was asked for; before, its scoreboard is read from the
    answer Steam gave for it.
    """
    p = MatchPlayer
    found = session.get(Match, match_id)
    if found is not None:
        players = _rows(
            session,
            select(*(getattr(p, column) for column in SCOREBOARD), Account.label)
            .outerjoin(Account, and_(Account.account_id == p.account_id, Account.active))
            .where(p.match_id == match_id)
            .order_by(p.player_slot),
        )
    elif (league := session.get(LeagueMatch, match_id)) is not None:
        found, rows = match_rows(league.raw_json)
        players = [
            {**{column: getattr(row, column) for column in SCOREBOARD}, "label": None}
            for row in sorted(rows, key=lambda row: row.player_slot)
        ]
    else:
        return None
    result = {
        "match_id": match_id, "start_time": found.start_time, "duration": found.duration,
        "radiant_win": found.radiant_win, "game_mode": found.game_mode, "lobby_type": found.lobby_type,
        "replay_state": found.replay_state or "none", "players": players,
    }  # fmt: skip
    for model in TABLES:
        table = model.__table__
        columns = [c for c in table.columns if c.name not in ("id", "match_id")]
        # primary key order is insertion order for the id tables and (player, minute) order for the rest
        statement = select(*columns).where(table.c.match_id == match_id).order_by(*table.primary_key.columns)
        result[table.name] = _rows(session, statement)
    return result


def _my_metrics(*columns):
    return _mine(*columns).join(
        Metric, and_(Metric.match_id == MatchPlayer.match_id, Metric.player_slot == MatchPlayer.player_slot)
    )


def metric(session: Session, where: list, name: str) -> list[dict]:
    """One metric's value in each parsed match of the account, oldest first."""
    return _rows(
        session,
        _my_metrics(Match.match_id, Match.start_time, Metric.value)
        .where(Metric.name == name, *where)
        .order_by(Match.start_time),
    )


def metric_averages(session: Session, where: list) -> list[dict]:
    """Every metric's average for the account, with the number of matches it is taken over."""
    return _rows(
        session,
        _my_metrics(Metric.name, func.avg(Metric.value).label("average"), func.count().label("matches"))
        .where(*where)
        .group_by(Metric.name),
    )


def teams(session: Session) -> list[dict]:
    """Every team with a stored league game, by name. A side that played without a team is not one."""
    m = LeagueMatch
    found: dict[int, dict] = {}
    columns = (m.radiant_team_id, m.dire_team_id, m.radiant_name, m.dire_name, m.radiant_win, m.start_time)
    for g in session.execute(select(*columns).order_by(m.start_time)):  # oldest first: the newest name and time stay
        sides = ((g.radiant_team_id, g.radiant_name, g.radiant_win), (g.dire_team_id, g.dire_name, not g.radiant_win))
        for team_id, name, win in sides:
            if team_id:
                t = found.setdefault(team_id, {"team_id": team_id, "games": 0, "wins": 0})
                # Steam sends some games with an empty team name: the last name it did send stays
                name = name or t.get("name")
                t.update(name=name, games=t["games"] + 1, wins=t["wins"] + win, last_played=g.start_time)
    return sorted(found.values(), key=lambda t: (t["name"] or "").lower())


def team(
    session: Session,
    team_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    league_id: int | None = None,
) -> dict | None:
    """One team's league games, newest first, and what they add up to. None for a team without a stored game.

    A hero is open in a game when neither side banned it and the other side did not pick it, so banned_against +
    banned + picked_against + open is the number of games. A player's wards come from the games whose replay is
    parsed (`replays` says how many of the player's games those are). The dates and the league narrow the games
    counted; a team with no game in them has an empty answer, not None.
    """
    names = {t["team_id"]: t["name"] for t in teams(session)}
    if team_id not in names:
        return None
    m = LeagueMatch
    where = [or_(m.radiant_team_id == team_id, m.dire_team_id == team_id), *between(m.start_time, date_from, date_to)]
    if league_id is not None:
        where.append(m.league_id == league_id)
    rows = session.scalars(select(m).where(*where).order_by(m.start_time.desc())).all()
    games = []
    heroes: dict[int, dict] = {}
    players: dict[int, dict] = {}

    def hero(hero_id: int) -> dict:
        blank = {"hero_id": hero_id, "banned_against": 0, "banned": 0, "picked_against": 0, "picked": 0, "wins": 0}
        return heroes.setdefault(hero_id, blank)

    ids = [g.match_id for g in rows]
    parsed = set(session.scalars(select(Match.match_id).where(Match.match_id.in_(ids), Match.replay_state == "parsed")))
    placed_by: dict[tuple[int, int], dict] = {}  # (match, player slot) -> the player
    for g in rows:
        radiant = g.radiant_team_id == team_id
        win = radiant == g.radiant_win
        opponent = g.dire_team_id if radiant else g.radiant_team_id
        bans = [b for b in g.raw_json.get("picks_bans") or [] if not b["is_pick"]]
        own = [b["hero_id"] for b in bans if (b["team"] == 0) == radiant]  # the draft calls Radiant team 0
        against = [b["hero_id"] for b in bans if (b["team"] == 0) != radiant]
        # picks come from the players, so a game without a recorded draft still has them; in slot order, so that
        # the site can tell which pick is which player slot
        ten = sorted(g.raw_json["players"], key=lambda p: p["player_slot"])
        side = [p for p in ten if (p["player_slot"] < 128) == radiant]
        for p in ten:
            if p not in side:
                hero(p["hero_id"])["picked_against"] += 1
        for hero_id in own:
            hero(hero_id)["banned"] += 1
        for hero_id in against:
            hero(hero_id)["banned_against"] += 1
        for p in side:
            hero(p["hero_id"])["picked"] += 1
            hero(p["hero_id"])["wins"] += win
            if p.get("account_id") in (None, ANONYMOUS):
                continue
            blank = {"account_id": p["account_id"], "games": 0, "replays": 0, "heroes": {}, "wards": []}
            player = players.setdefault(p["account_id"], blank)
            player["games"] += 1
            player["replays"] += g.match_id in parsed
            placed_by[g.match_id, p["player_slot"]] = player
            blank = {"hero_id": p["hero_id"], "games": 0, "wins": 0, **dict.fromkeys(AVERAGED, 0)}
            on = player["heroes"].setdefault(p["hero_id"], blank)
            on.update(games=on["games"] + 1, wins=on["wins"] + win)
            for stat in AVERAGED:
                on[stat] += p.get(stat) or 0
        games.append(
            {
                "match_id": g.match_id, "start_time": g.start_time, "league": LEAGUES.get(g.league_id, str(g.league_id)),
                "radiant": radiant, "win": win, "opponent_id": opponent, "opponent": names.get(opponent),
                "picks": [p["hero_id"] for p in side], "picks_against": [p["hero_id"] for p in ten if p not in side],
                "bans": own, "bans_against": against,
                "replay": g.match_id in parsed,
            }
        )  # fmt: skip
    for h in heroes.values():
        h["open"] = len(rows) - h["banned_against"] - h["banned"] - h["picked_against"]
    w = Ward
    for ward in session.execute(select(w.match_id, w.player_slot, w.type, w.x, w.y).where(w.match_id.in_(ids))):
        if (ward.match_id, ward.player_slot) in placed_by:
            placed_by[ward.match_id, ward.player_slot]["wards"].append(
                {"type": ward.type, "x": ward.x, "y": ward.y, "radiant": ward.player_slot < 128}
            )
    n = PlayerName
    known = dict(session.execute(select(n.account_id, n.name).where(n.account_id.in_(players))).all())
    for player in players.values():
        player["name"] = known.get(player["account_id"])
        player["heroes"] = sorted(player["heroes"].values(), key=lambda h: -h["games"])
        for h in player["heroes"]:
            h.update({stat: h[stat] / h["games"] for stat in AVERAGED})
    return {
        "team_id": team_id, "name": names[team_id], "games": games,
        "heroes": sorted(heroes.values(), key=lambda h: (-h["banned_against"], -h["picked"])),
        "players": sorted(players.values(), key=lambda p: -p["games"]),
    }  # fmt: skip
