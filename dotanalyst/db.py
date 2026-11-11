from pathlib import Path

from sqlalchemy import JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATA = Path("data")


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str | None]
    active: Mapped[bool] = mapped_column(default=True)
    # None until the first sync; False when Steam answers status 15
    history_exposed: Mapped[bool | None]


class Match(Base):
    __tablename__ = "matches"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    match_seq_num: Mapped[int]
    start_time: Mapped[int]
    duration: Mapped[int]
    radiant_win: Mapped[bool]
    game_mode: Mapped[int]
    lobby_type: Mapped[int]
    cluster: Mapped[int]
    raw_json: Mapped[dict] = mapped_column(JSON)
    # none | pending | parsed | unavailable | failed
    replay_state: Mapped[str] = mapped_column(default="none")
    replay_tried_at: Mapped[int | None]


class MatchPlayer(Base):
    __tablename__ = "match_players"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    player_slot: Mapped[int] = mapped_column(primary_key=True)  # 0-4 Radiant, 128-132 Dire
    account_id: Mapped[int | None] = mapped_column(index=True)  # None when anonymous
    hero_id: Mapped[int]
    items: Mapped[list] = mapped_column(JSON)  # item_0..item_5, then item_neutral
    kills: Mapped[int | None]
    deaths: Mapped[int | None]
    assists: Mapped[int | None]
    last_hits: Mapped[int | None]
    denies: Mapped[int | None]
    gold_per_min: Mapped[int | None]
    xp_per_min: Mapped[int | None]
    net_worth: Mapped[int | None]
    level: Mapped[int | None]
    hero_damage: Mapped[int | None]
    tower_damage: Mapped[int | None]
    hero_healing: Mapped[int | None]
    leaver_status: Mapped[int | None]


class Hero(Base):
    __tablename__ = "heroes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]  # npc_dota_hero_*, as used in replay events
    localized_name: Mapped[str]


def open_session() -> Session:
    DATA.mkdir(exist_ok=True)
    engine = create_engine(f"sqlite:///{DATA / 'dotanalyst.db'}")
    Base.metadata.create_all(engine)
    return Session(engine)
