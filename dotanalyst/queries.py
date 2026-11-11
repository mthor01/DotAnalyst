"""Aggregations over stored matches. Every query is seen from one tracked account's side."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, aliased

from .db import Account, Match, MatchPlayer

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
    p = MatchPlayer
    return _rows(
        session,
        _mine(
            Match.match_id, Match.start_time, Match.duration, Match.game_mode, Match.lobby_type,
            Match.replay_state, WON.label("win"), p.hero_id, p.kills, p.deaths, p.assists,
            p.last_hits, p.denies, p.gold_per_min, p.xp_per_min, p.net_worth, p.items,
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
