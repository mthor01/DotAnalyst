"""Aggregations over stored matches. Every query is seen from one tracked account's side, or from one league team's."""
from collections import Counter
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from .db import (
    TABLES, Account, Death, Lane, LeagueMatch, Match, MatchPlayer, Metric, PlayerGame, PlayerGameList, PlayerMinute,
    PlayerName, Tormentor, Ward, WisdomRune,
)  # fmt: skip
from .replay import MAX_AGE_DAYS
from .steam import ANONYMOUS, leagues, match_rows

OTHER = aliased(MatchPlayer)
IS_RADIANT = MatchPlayer.player_slot < 128
WON = case((IS_RADIANT == Match.radiant_win, 1), else_=0)
SAME_TEAM = (OTHER.player_slot < 128) == IS_RADIANT
SCOREBOARD = (
    "player_slot", "account_id", "hero_id", "kills", "deaths", "assists", "last_hits", "denies", "gold_per_min",
    "xp_per_min", "net_worth", "level", "hero_damage", "tower_damage", "hero_healing", "items",
)  # fmt: skip
AVERAGED = ("kills", "deaths", "assists", "last_hits", "gold_per_min", "xp_per_min")  # of a league player on a hero
RECENT = 10  # a team's newest games, whose most frequent five players are its main stack
TEAMMATE_MATCHES, TEAMMATE_GAMES = 500, 10  # "add teammates": this many games together in the newest this many
PARTY_TOGETHER = 5  # matches on the same team after which a teammate counts as someone the player queues with
LANE_ROLES = {1: "safe", 2: "mid", 3: "off", 4: "jungle"}  # OpenDota's lane_role, as the role wheel names them


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
    hero_id: int | None = None,
) -> list:
    """SQL conditions for the filters every view shares. Dates are local days, both inclusive; `hero_id` is the
    player's own hero."""
    found = [MatchPlayer.account_id == account_id, *between(Match.start_time, date_from, date_to)]
    if league_id is not None:
        found.append(Match.match_id.in_(select(LeagueMatch.match_id).where(LeagueMatch.league_id == league_id)))
    if game_mode is not None:
        found.append(Match.game_mode == game_mode)
    if lobby_type is not None:
        found.append(Match.lobby_type == lobby_type)
    if hero_id is not None:
        found.append(MatchPlayer.hero_id == hero_id)
    return found


def narrowed(
    session: Session, where: list, position: list[int] | None = None, party: bool | None = None, last: int | None = None
) -> list:
    """`where` narrowed to the matches in which the player took one of the positions `position` (see positions) and
    queued in a party (`party` True) or alone (False), see _parties; then to the newest `last` of those. None or an
    empty list narrows nothing."""
    if position or party is not None:
        found, parties = _positions(session, where), _parties(session, where) if party is not None else set()
        mine = session.execute(_mine(MatchPlayer.match_id, MatchPlayer.player_slot).where(*where))
        kept = [m for m, slot in mine if (not position or found[m, slot] in position) and (party is None or (m in parties) == party)]
        where = [*where, Match.match_id.in_(kept)]
    if last is not None:
        # correlate(None): the subquery has its own Match and MatchPlayer, not the outer query's
        newest = _mine(Match.match_id).where(*where).order_by(Match.start_time.desc()).limit(last).correlate(None)
        where = [*where, Match.match_id.in_(newest)]
    return where


def _mine(*columns):
    # select_from pins "my" row as the left side even when the first column comes from OTHER
    return select(*columns).select_from(MatchPlayer).join(Match, Match.match_id == MatchPlayer.match_id)


def _rows(session: Session, statement) -> list[dict]:
    return [dict(row._mapping) for row in session.execute(statement)]


def positions(team: list[dict]) -> dict[int, int]:
    """Position 1-5 of each player of one team, by player_slot. A player is a dict of player_slot, last_hits,
    net_worth and lane: safe | mid | off | jungle, seen from the team's side, or None without a parsed replay.

    The farm (last hits, then net worth) picks within a lane: the safe lane's most farmed is 1 and least farmed 5,
    the mid's is 2, the off lane's 3 and 4. Whoever is left (jungle, roaming, a third in a lane, no replay) takes the
    open positions in order of farm.
    """
    farm = lambda p: (p["last_hits"] or 0, p["net_worth"] or 0)  # noqa: E731
    found: dict[int, int] = {}
    for lane, places in (("safe", (1, 5)), ("mid", (2,)), ("off", (3, 4))):
        laners = sorted((p for p in team if p["lane"] == lane), key=farm, reverse=True)
        if len(laners) == 1:
            places = places[:1]
        found.update(zip((p["player_slot"] for p in laners), places))
    rest = sorted((p for p in team if p["player_slot"] not in found), key=farm, reverse=True)
    found.update(zip((p["player_slot"] for p in rest), (n for n in range(1, 6) if n not in found.values())))
    return found


def _positions(session: Session, where: list) -> dict[tuple[int, int], int]:
    """Position of every player in the matches `where` finds, by (match_id, player_slot)."""
    return _positions_in(session, _mine(MatchPlayer.match_id).where(*where))


def _positions_in(session: Session, played) -> dict[tuple[int, int], int]:
    """Position of every player in the matches `played` lists, by (match_id, player_slot)."""
    rows = session.execute(
        select(OTHER.match_id, OTHER.player_slot, OTHER.last_hits, OTHER.net_worth, Lane.lane)
        .outerjoin(Lane, and_(Lane.match_id == OTHER.match_id, Lane.player_slot == OTHER.player_slot))
        .where(OTHER.match_id.in_(played))
    )
    teams: dict[tuple[int, bool], list[dict]] = {}
    for r in rows:
        radiant = r.player_slot < 128
        safe = "bot" if radiant else "top"  # Radiant's safe lane is bottom, Dire's is top
        lane = r.lane if r.lane not in ("top", "bot") else "safe" if r.lane == safe else "off"
        teams.setdefault((r.match_id, radiant), []).append({**r._asdict(), "lane": lane})
    return {(match_id, slot): n for (match_id, _), team in teams.items() for slot, n in positions(team).items()}


ROW_METRICS = (
    "lane_nw_diff", "obs_bought", "sen_bought", "wards_destroyed", "obs_lifetime", "lane_cs_diff", "lane_dn_diff", "last_hits_at_10",
    "denies_at_10", "net_worth_at_10", "xp_at_10", "damage_at_10", "damage_taken_at_10", "lane_damage_at_10",
    "enemy_lane_damage_at_10", "kills_by_10", "deaths_by_10", "camps_pulled_by_10", "camps_stacked",
    "kill_participation", "fight_participation", "deaths_outside_fights",
)  # fmt: skip


def _laners(session: Session, where: list) -> dict[tuple[int, int], tuple[list[int], list[int]]]:
    """The heroes in each player's lane (top, mid or bot) as (allies, enemies), the player left out, by (match_id,
    player_slot), for the matches `where` finds. A player outside the three lanes or without a parsed replay has no entry."""
    rows = session.execute(
        select(OTHER.match_id, OTHER.player_slot, OTHER.hero_id, Lane.lane)
        .join(Lane, and_(Lane.match_id == OTHER.match_id, Lane.player_slot == OTHER.player_slot))
        .where(OTHER.match_id.in_(_mine(MatchPlayer.match_id).where(*where)), Lane.lane.in_(("top", "mid", "bot")))
    )
    lanes: dict[tuple[int, str], list[tuple[int, int]]] = {}
    for r in rows:
        lanes.setdefault((r.match_id, r.lane), []).append((r.player_slot, r.hero_id))
    return {
        (match_id, slot): (
            [hero for other, hero in laners if other != slot and (other < 128) == (slot < 128)],
            [hero for other, hero in laners if (other < 128) != (slot < 128)],
        )
        for (match_id, _), laners in lanes.items()
        for slot, _ in laners
    }


def _parties(session: Session, where: list) -> dict[int, int]:
    """The matches `where` finds in which the player queued with someone, with the party's size: OpenDota's party size
    where it is stored, otherwise 1 + the teammates who were on the player's team in at least PARTY_TOGETHER stored
    matches (a floor: hidden accounts don't count). Solo matches are left out."""
    known = {r.match_id: r.party_size for r in session.execute(
        _mine(MatchPlayer.match_id, MatchPlayer.party_size).where(*where, MatchPlayer.party_size.is_not(None))
    )}  # fmt: skip
    beside = and_(
        OTHER.match_id == MatchPlayer.match_id, OTHER.account_id != MatchPlayer.account_id,
        OTHER.account_id != ANONYMOUS, SAME_TEAM,
    )  # fmt: skip
    seen = session.execute(_mine(MatchPlayer.match_id, MatchPlayer.account_id, OTHER.account_id).join(OTHER, beside).where(*where)).all()
    together = Counter(
        session.execute(
            select(OTHER.account_id).select_from(MatchPlayer).join(OTHER, beside)
            .where(MatchPlayer.account_id.in_({me for _, me, _ in seen}))
        ).scalars()
    )  # shortcut: counts teammates of every account `where` names together, right while it names one
    guessed = Counter(match_id for match_id, _, mate in seen if together[mate] >= PARTY_TOGETHER)
    return {m: 1 + mates for m, mates in guessed.items() if m not in known} | {m: n for m, n in known.items() if n > 1}


def matches(session: Session, where: list) -> list[dict]:
    """The account's matches, newest first. `lane` and the ROW_METRICS are None without a parsed replay; `position`
    is 1-5, see positions; `lane_allies` and `lane_enemies` the other heroes in the player's lane, see _laners; `party_size`
    1 when the player queued alone, see _parties."""
    p = MatchPlayer
    joined = {name: aliased(Metric) for name in ROW_METRICS}
    with_tracked = (
        select(OTHER.match_id)
        .join(Account, and_(Account.account_id == OTHER.account_id, Account.active))
        .where(OTHER.match_id == p.match_id, OTHER.account_id != p.account_id, SAME_TEAM)
        .exists()
    )
    statement = (
        _mine(
            Match.match_id, Match.start_time, Match.duration, Match.game_mode, Match.lobby_type,
            Match.replay_state, WON.label("win"), p.player_slot, p.hero_id, p.kills, p.deaths, p.assists,
            p.last_hits, p.denies, p.gold_per_min, p.xp_per_min, p.net_worth, p.items,
            IS_RADIANT.label("radiant"), Lane.lane, *(m.value.label(name) for name, m in joined.items()),
            with_tracked.label("with_tracked"),
        )
        .outerjoin(Lane, and_(Lane.match_id == p.match_id, Lane.player_slot == p.player_slot))
        .where(*where)
        .order_by(Match.start_time.desc())
    )
    for name, m in joined.items():
        statement = statement.outerjoin(
            m, and_(m.match_id == p.match_id, m.player_slot == p.player_slot, m.name == name)
        )
    rows = _rows(session, statement)
    found, laners, parties = _positions(session, where), _laners(session, where), _parties(session, where)
    for r in rows:
        key = r["match_id"], r.pop("player_slot")
        r["position"], r["party_size"] = found[key], parties.get(r["match_id"], 1)
        r["lane_allies"], r["lane_enemies"] = laners.get(key, ([], []))
    return rows


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


def frequent_teammates(session: Session, account_id: int) -> list[int]:
    """Every player, tracked or not, on the account's team in at least TEAMMATE_GAMES of its newest
    TEAMMATE_MATCHES matches, most games first. Anonymous players are nobody."""
    games = func.count()
    return list(
        session.scalars(
            _mine(OTHER.account_id)
            .join(OTHER, and_(OTHER.match_id == MatchPlayer.match_id, OTHER.account_id != MatchPlayer.account_id, SAME_TEAM))
            .where(*narrowed(session, conditions(account_id), last=TEAMMATE_MATCHES), OTHER.account_id != ANONYMOUS)
            .group_by(OTHER.account_id)
            .having(games >= TEAMMATE_GAMES)
            .order_by(games.desc(), OTHER.account_id)
        )
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
    """Every ward the account placed in its parsed matches: the match, the kind, the place, the side played,
    whether that match was won and whether the enemy destroyed the ward."""
    ward = and_(Ward.match_id == MatchPlayer.match_id, Ward.player_slot == MatchPlayer.player_slot)
    columns = (
        Match.match_id, Ward.type, Ward.x, Ward.y, IS_RADIANT.label("radiant"), Ward.placed.label("time"),
        (IS_RADIANT == Match.radiant_win).label("win"), Ward.killed,
    )  # fmt: skip
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
    ids = [p["account_id"] for p in players if p["account_id"]]
    names = dict(session.execute(select(PlayerName.account_id, PlayerName.name).where(PlayerName.account_id.in_(ids))).all())
    tracked = set(session.scalars(select(Account.account_id).where(Account.active, Account.account_id.in_(ids))))
    for player in players:
        player["name"], player["tracked"] = names.get(player["account_id"]), player["account_id"] in tracked
    result = {
        "match_id": match_id, "start_time": found.start_time, "duration": found.duration,
        "radiant_win": found.radiant_win, "game_mode": found.game_mode, "lobby_type": found.lobby_type,
        "replay_state": found.replay_state or "none", "players": players,
        "draft": [
            {"hero_id": b["hero_id"], "pick": b["is_pick"], "radiant": b["team"] == 0}
            for b in sorted(found.raw_json.get("picks_bans") or [], key=lambda b: b["order"])
        ],
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


def metric_averages(session: Session, where: list) -> list[dict]:
    """Every metric's average for the account, with the number of matches it is taken over."""
    return _rows(
        session,
        _my_metrics(Metric.name, func.avg(Metric.value).label("average"), func.count().label("matches"))
        .where(*where)
        .group_by(Metric.name),
    )


def tournaments(session: Session) -> list[dict]:
    """Every tracked tournament, the newest id first, with its stored games, its teams and its first and last game."""
    m = LeagueMatch
    found = {
        i: {"league_id": i, "name": n, "games": 0, "teams": set(), "first_game": None, "last_game": None}
        for i, n in leagues(session).items()
    }
    for g in session.execute(select(m.league_id, m.radiant_team_id, m.dire_team_id, m.start_time).order_by(m.start_time)):
        if (t := found.get(g.league_id)) is not None:
            t["teams"].update(team for team in (g.radiant_team_id, g.dire_team_id) if team)  # 0 is no team
            t.update(games=t["games"] + 1, first_game=t["first_game"] or g.start_time, last_game=g.start_time)
    return [{**t, "teams": len(t["teams"])} for t in reversed(found.values())]


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


def _logo_id(session: Session, team_id: int) -> int | None:
    """The UGC id of the team's logo in its newest league game that has one, whatever the filters."""
    m = LeagueMatch
    for g in session.scalars(
        select(m).where(or_(m.radiant_team_id == team_id, m.dire_team_id == team_id)).order_by(m.start_time.desc())
    ):
        logo = g.raw_json.get("radiant_logo" if g.radiant_team_id == team_id else "dire_logo")
        if logo:
            return logo
    return None


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
    parsed (`replays` says how many of the player's games those are), and from their parsed games outside any
    league (`usual_replays`, wards with `league` False). `usual_waiting` counts the usual games whose replay the
    poller still means to get, None for a player whose team was never checked. `main` marks the five players with the
    most of the team's newest RECENT games (the newer last game breaks a tie), the others stand in. `position` is
    the position 1-5 a player took most often in these games (the newest breaks a tie): from the replay where it is
    parsed, else from the farm and OpenDota's lane_role, as `positions` works it out. The dates and the league narrow the games counted; a team
    with no game in them has an empty answer, not None.
    """
    names = {t["team_id"]: t["name"] for t in teams(session)}
    tournament = leagues(session)
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
    states = dict(session.execute(select(Match.match_id, Match.replay_state).where(Match.match_id.in_(ids))).all())
    parsed = {m for m, state in states.items() if state == "parsed"}
    placed_by: dict[tuple[int, int], dict] = {}  # (match, player slot) -> the player
    side_of = {g.match_id: g.radiant_team_id == team_id for g in rows if g.match_id in parsed}  # True: Radiant
    tormentor, blood = _first_tormentors(session, side_of), _first_bloods(session, side_of)
    replay_positions = _positions_in(session, list(side_of))
    recent = {g.match_id for g in rows[:RECENT]}
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
        farmed = positions(
            [{"player_slot": p["player_slot"], "last_hits": p.get("last_hits"), "net_worth": p.get("net_worth"),
              "lane": LANE_ROLES.get(p.get("lane_role"))} for p in side]
        )  # fmt: skip
        for p in side:
            hero(p["hero_id"])["picked"] += 1
            hero(p["hero_id"])["wins"] += win
            if p.get("account_id") in (None, ANONYMOUS):
                continue
            blank = {
                "account_id": p["account_id"], "games": 0, "recent": 0, "last_played": g.start_time, "replays": 0,
                "usual_replays": 0, "heroes": {}, "wards": [], "parsed": [], "positions": Counter(),
            }  # fmt: skip
            player = players.setdefault(p["account_id"], blank)  # rows are newest first: last_played is their newest
            player["games"] += 1
            player["positions"][replay_positions.get((g.match_id, p["player_slot"]), farmed[p["player_slot"]])] += 1
            player["recent"] += g.match_id in recent
            player["replays"] += g.match_id in parsed
            if g.match_id in parsed:  # the ward map's games, wards or none
                player["parsed"].append({"radiant": radiant, "league": True, "win": win})
            placed_by[g.match_id, p["player_slot"]] = player, win
            blank = {"hero_id": p["hero_id"], "games": 0, "wins": 0, **dict.fromkeys(AVERAGED, 0)}
            on = player["heroes"].setdefault(p["hero_id"], blank)
            on.update(games=on["games"] + 1, wins=on["wins"] + win)
            for stat in AVERAGED:
                on[stat] += p.get(stat) or 0
        games.append(
            {
                "match_id": g.match_id, "start_time": g.start_time, "league": tournament.get(g.league_id, str(g.league_id)),
                "radiant": radiant, "win": win, "opponent_id": opponent, "opponent": names.get(opponent),
                "picks": [p["hero_id"] for p in side], "picks_against": [p["hero_id"] for p in ten if p not in side],
                "bans": own, "bans_against": against,
                "replay": g.match_id in parsed, "replay_state": states.get(g.match_id), "tormentor": tormentor.get(g.match_id), "first_blood": blood.get(g.match_id),
            }
        )  # fmt: skip
    for h in heroes.values():
        h["open"] = len(rows) - h["banned_against"] - h["banned"] - h["picked_against"]
    # their parsed games outside any league, for the ward map's usual matches: only the dates narrow them
    mp = MatchPlayer
    usual = (
        select(mp.account_id, mp.match_id, mp.player_slot, Match.radiant_win)
        .join(Match, Match.match_id == mp.match_id)
        .where(
            mp.account_id.in_(players), Match.replay_state == "parsed",
            Match.match_id.not_in(select(LeagueMatch.match_id)), *between(Match.start_time, date_from, date_to),
        )
    )  # fmt: skip
    for row in session.execute(usual):
        win = (row.player_slot < 128) == row.radiant_win
        players[row.account_id]["usual_replays"] += 1
        players[row.account_id]["parsed"].append({"radiant": row.player_slot < 128, "league": False, "win": win})
        placed_by[row.match_id, row.player_slot] = players[row.account_id], win
    w = Ward
    league_ids = set(ids)
    placed_in = {match_id for match_id, _ in placed_by}
    for ward in session.execute(select(w.match_id, w.player_slot, w.type, w.x, w.y, w.placed).where(w.match_id.in_(placed_in))):  # fmt: skip
        if (ward.match_id, ward.player_slot) in placed_by:
            player, win = placed_by[ward.match_id, ward.player_slot]
            player["wards"].append(
                {
                    "match_id": ward.match_id, "type": ward.type, "x": ward.x, "y": ward.y, "radiant": ward.player_slot < 128, "time": ward.placed,
                    "league": ward.match_id in league_ids, "win": win,
                }
            )  # fmt: skip
    n = PlayerName
    known = {r.account_id: r for r in session.execute(select(n.account_id, n.name, n.avatar).where(n.account_id.in_(players)))}
    tracked = dict(session.execute(select(Account.account_id, Account.avatar).where(Account.active, Account.account_id.in_(players))).all())
    stack = sorted((p for p in players.values() if p["recent"]), key=lambda p: (-p["recent"], -p["last_played"]))[:5]
    stack = {p["account_id"] for p in stack}
    # their games outside the league, for the role wheel: the time and season filters do not apply to them
    pgl = PlayerGameList
    listed = dict(session.execute(select(pgl.account_id, pgl.replays_wanted).where(pgl.account_id.in_(players))).all())
    wanted = [account_id for account_id, replays_wanted in listed.items() if replays_wanted]
    # of a checked team's players: their usual games young enough whose replay the poller has not got to yet
    waiting = dict(
        session.execute(
            select(PlayerGame.account_id, func.count())
            .outerjoin(Match, Match.match_id == PlayerGame.match_id)
            .where(
                PlayerGame.account_id.in_(wanted), PlayerGame.start_time > datetime.now().timestamp() - MAX_AGE_DAYS * 86400,
                or_(Match.match_id.is_(None), Match.replay_state.in_(("none", "pending"))),
            )
            .group_by(PlayerGame.account_id)
        ).all()
    )  # fmt: skip
    outside = {account_id: [] for account_id in players}
    pg = PlayerGame
    for g in session.scalars(select(pg).where(pg.account_id.in_(players)).order_by(pg.start_time.desc())):
        outside[g.account_id].append(
            {
                "match_id": g.match_id, "hero_id": g.hero_id, "win": (g.player_slot < 128) == g.radiant_win,
                "role": LANE_ROLES.get(g.lane_role, "none"), "kills": g.kills, "deaths": g.deaths, "assists": g.assists,
            }
        )  # fmt: skip
    for player in players.values():
        name = known.get(player["account_id"])
        player["name"] = name and name.name
        player["avatar"] = name and name.avatar or tracked.get(player["account_id"]) or None
        player["tracked"] = player["account_id"] in tracked
        player["main"] = player["account_id"] in stack
        player["position"] = player.pop("positions").most_common(1)[0][0]  # ties: the first counted, the newest
        player["outside_listed"] = player["account_id"] in listed
        player["usual_waiting"] = waiting.get(player["account_id"], 0) if player["account_id"] in wanted else None
        player["outside"] = outside[player["account_id"]]
        player["heroes"] = sorted(player["heroes"].values(), key=lambda h: -h["games"])
        for h in player["heroes"]:
            h.update({stat: h[stat] / h["games"] for stat in AVERAGED})
    firsts = list(tormentor.values())
    return {
        "team_id": team_id, "name": names[team_id], "logo_id": _logo_id(session, team_id), "games": games,
        "heroes": sorted(heroes.values(), key=lambda h: (-h["banned_against"], -h["picked"])),
        "players": sorted(players.values(), key=lambda p: -p["games"]),
        "tormentors": {"games": len(side_of), "them": _tormentors_by(firsts, True), "enemy": _tormentors_by(firsts, False)},
        "lanes": _team_lanes(session, side_of), "wisdom": _team_wisdom(session, side_of),
        "draft": _team_draft(session, [g for g in rows if g.match_id in parsed], side_of),
    }  # fmt: skip


def _mean(values: list) -> float | None:
    return sum(values) / len(values) if values else None


def _first_tormentors(session: Session, side_of: dict[int, bool]) -> dict[int, dict]:
    """Each parsed game's first Tormentor, from the team's side: when, whether the team took it, the dead heroes of
    the side that did not take it, and the taker's net worth lead (negative: behind)."""
    first: dict[int, dict] = {}
    for k in session.scalars(select(Tormentor).where(Tormentor.match_id.in_(side_of)).order_by(Tormentor.time, Tormentor.id)):
        if k.match_id not in first:
            first[k.match_id] = {
                "time": k.time, "taken": k.radiant == side_of[k.match_id], "enemies_dead": k.enemies_dead,
                "lead": k.radiant_lead if k.radiant else -k.radiant_lead,
            }  # fmt: skip
    return first


def _tormentors_by(firsts: list[dict], taken: bool) -> dict:
    """The first Tormentors one side took (the team: `taken` True): how many, and their mean time, enemies dead and lead."""
    found = [t for t in firsts if t["taken"] == taken]
    return {"count": len(found), **{key: _mean([t[key] for t in found]) for key in ("time", "enemies_dead", "lead")}}


def _first_bloods(session: Session, side_of: dict[int, bool]) -> dict[int, bool]:
    """Whether the team drew each parsed game's first blood: the first death not at the hands of the dead hero's own
    side. A death to creeps, towers or neutrals counts for the other side."""
    found: dict[int, bool] = {}
    for d in session.scalars(select(Death).where(Death.match_id.in_(side_of)).order_by(Death.time, Death.id)):
        denied = d.killer_slot is not None and (d.killer_slot < 128) == (d.player_slot < 128)
        if d.match_id not in found and not denied:
            found[d.match_id] = (d.player_slot < 128) != side_of[d.match_id]
    return found


LANE_MINUTE = 10


def _team_lanes(session: Session, side_of: dict[int, bool]) -> dict:
    """The team's safe, mid and off lane at 10:00 of the parsed games where both sides had heroes in it: in how many
    games, in how many the team was ahead in net worth, and its mean net worth and experience lead there."""
    lane_of = {(r.match_id, r.player_slot): r.lane for r in session.scalars(select(Lane).where(Lane.match_id.in_(side_of)))}
    totals: dict[tuple[int, str], list[int]] = {}  # (match, lane on the map) -> [own heroes, enemies, net worth, xp]
    pm = PlayerMinute
    for r in session.scalars(select(pm).where(pm.match_id.in_(side_of), pm.minute == LANE_MINUTE)):
        lane = lane_of.get((r.match_id, r.player_slot))
        if lane not in ("top", "mid", "bot"):
            continue
        ours = (r.player_slot < 128) == side_of[r.match_id]
        t = totals.setdefault((r.match_id, lane), [0, 0, 0, 0])
        t[0 if ours else 1] += 1
        t[2] += r.net_worth if ours else -r.net_worth
        t[3] += r.xp if ours else -r.xp
    found: dict[str, list[tuple[int, int]]] = {"safe": [], "mid": [], "off": []}
    for (match_id, lane), (own, enemies, net_worth, xp) in totals.items():
        if own and enemies:  # a lead needs both sides in the lane
            safe = "bot" if side_of[match_id] else "top"
            found["mid" if lane == "mid" else "safe" if lane == safe else "off"].append((net_worth, xp))
    return {
        name: {
            "games": len(leads), "ahead": sum(nw > 0 for nw, _ in leads),
            "net_worth": _mean([nw for nw, _ in leads]), "xp": _mean([xp for _, xp in leads]),
        }  # fmt: skip
        for name, leads in found.items()
    }


def _team_wisdom(session: Session, side_of: dict[int, bool]) -> dict:
    """The wisdom runes of the team's parsed games, its own (in its half of the map) and the enemy's: how many
    appeared, how many it came for, with how many heroes and what net worth lead, how many it took, and the heroes
    that died at them per game: the enemy's are its kills, its own its deaths."""
    found: dict[str, list[WisdomRune]] = {"own": [], "enemy": []}
    for r in session.scalars(select(WisdomRune).where(WisdomRune.match_id.in_(side_of))):
        found["own" if (r.rune == "radiant") == side_of[r.match_id] else "enemy"].append(r)

    def summary(runes: list[WisdomRune]) -> dict:
        def heroes(r: WisdomRune) -> int:
            return r.radiant_heroes if side_of[r.match_id] else r.dire_heroes

        came = [r for r in runes if heroes(r)]
        games = len({r.match_id for r in runes})
        kills = sum(r.dire_deaths if side_of[r.match_id] else r.radiant_deaths for r in runes)
        deaths = sum(r.radiant_deaths if side_of[r.match_id] else r.dire_deaths for r in runes)
        return {
            "spawns": len(runes), "contested": len(came), "heroes": _mean([heroes(r) for r in came]),
            "taken": sum(r.taken_by_radiant is side_of[r.match_id] for r in runes),
            "lead": _mean([r.radiant_lead if side_of[r.match_id] else -r.radiant_lead for r in came]),
            "kills": kills / games if games else None, "deaths": deaths / games if games else None,
        }  # fmt: skip

    return {side: summary(runes) for side, runes in found.items()}


def _team_draft(session: Session, games: list[LeagueMatch], side_of: dict[int, bool]) -> list[list[int]]:
    """For the team's 1st to 5th pick in its parsed games, how often the hero played position 1, 2, 3, 4 and 5."""
    counts = [[0] * 5 for _ in range(5)]
    if not games:
        return counts
    position = _positions_in(session, list(side_of))
    for g in games:
        slot_of = {p["hero_id"]: p["player_slot"] for p in g.raw_json["players"]}
        picks = [b for b in g.raw_json.get("picks_bans") or [] if b["is_pick"] and (b["team"] == 0) == side_of[g.match_id]]
        for k, b in enumerate(sorted(picks, key=lambda b: b["order"])[:5]):
            if n := position.get((g.match_id, slot_of.get(b["hero_id"]))):
                counts[k][n - 1] += 1
    return counts
