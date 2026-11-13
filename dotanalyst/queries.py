"""Aggregations over stored matches. Every query is seen from one tracked account's side."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, aliased

from .db import TABLES, Account, Lane, Match, MatchPlayer, Metric

OTHER = aliased(MatchPlayer)
IS_RADIANT = MatchPlayer.player_slot < 128
WON = case((IS_RADIANT == Match.radiant_win, 1), else_=0)
SAME_TEAM = (OTHER.player_slot < 128) == IS_RADIANT


def conditions(
    account_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    game_mode: int | None = None,
    lobby_type: int | None = None,
) -> list:
    """SQL conditions for the filters every view shares. Dates are local days, both inclusive."""
    found = [MatchPlayer.account_id == account_id]
    if date_from is not None:
        found.append(Match.start_time >= datetime.combine(date_from, time.min).timestamp())
    if date_to is not None:
        found.append(Match.start_time < datetime.combine(date_to + timedelta(days=1), time.min).timestamp())
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


def match(session: Session, match_id: int) -> dict | None:
    """One match: the scoreboard, plus the replay stats where there are any (empty lists otherwise)."""
    found = session.get(Match, match_id)
    if found is None:
        return None
    p = MatchPlayer
    players = _rows(
        session,
        select(
            p.player_slot, p.account_id, Account.label, p.hero_id, p.kills, p.deaths, p.assists, p.last_hits,
            p.denies, p.gold_per_min, p.xp_per_min, p.net_worth, p.level, p.hero_damage, p.tower_damage,
            p.hero_healing, p.items,
        )
        .outerjoin(Account, and_(Account.account_id == p.account_id, Account.active))
        .where(p.match_id == match_id)
        .order_by(p.player_slot),
    )  # fmt: skip
    result = {
        "match_id": match_id, "start_time": found.start_time, "duration": found.duration,
        "radiant_win": found.radiant_win, "game_mode": found.game_mode, "lobby_type": found.lobby_type,
        "replay_state": found.replay_state, "players": players,
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
