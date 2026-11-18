from pathlib import Path

from sqlalchemy import JSON, Engine, create_engine, inspect
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
    avatar: Mapped[str | None]  # Steam profile picture URL; "" when Steam has none, None until asked


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


class LeagueMatch(Base):
    """A league game. Not in `matches`: there it would join the accounts' stats and have its replay downloaded."""

    __tablename__ = "league_matches"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int]
    start_time: Mapped[int]
    radiant_team_id: Mapped[int] = mapped_column(index=True)  # 0 when that side played without a team
    dire_team_id: Mapped[int] = mapped_column(index=True)
    radiant_name: Mapped[str | None]
    dire_name: Mapped[str | None]
    radiant_win: Mapped[bool]
    raw_json: Mapped[dict] = mapped_column(JSON)  # has picks_bans, the draft in order, and the ten players


class PlayerName(Base):
    """Steam name of a league player, as it was when first asked for."""

    __tablename__ = "player_names"

    account_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


class PlayerGameList(Base):
    """A league player whose games outside the league were asked of OpenDota, even when it had none to give."""

    __tablename__ = "player_game_lists"

    account_id: Mapped[int] = mapped_column(primary_key=True)
    fetched_at: Mapped[int]
    replays_wanted: Mapped[bool] = mapped_column(default=False)  # their team was checked: the poller gets replays of their games


class PlayerGame(Base):
    """One of a league player's last games outside the league, as OpenDota lists it. Its replay is fetched only
    when the player's list has replays_wanted, while the game is young enough."""

    __tablename__ = "player_games"

    account_id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(primary_key=True)
    start_time: Mapped[int]
    hero_id: Mapped[int]
    player_slot: Mapped[int]
    radiant_win: Mapped[bool]
    lobby_type: Mapped[int | None]
    game_mode: Mapped[int | None]
    kills: Mapped[int | None]
    deaths: Mapped[int | None]
    assists: Mapped[int | None]
    lane_role: Mapped[int | None]  # OpenDota's: 1 safe, 2 mid, 3 off, 4 jungle; None when it did not parse the game


class Hero(Base):
    __tablename__ = "heroes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]  # npc_dota_hero_*, as used in replay events
    localized_name: Mapped[str]


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]  # without the item_ prefix


class Ability(Base):
    __tablename__ = "abilities"

    name: Mapped[str] = mapped_column(primary_key=True)  # as in replay events; a talent is special_bonus_*
    dname: Mapped[str]  # the name the game shows; for a talent that is what it gives


class Recipe(Base):
    __tablename__ = "recipes"

    item: Mapped[str] = mapped_column(primary_key=True)  # without the item_ prefix, like Item.name
    components: Mapped[list] = mapped_column(JSON)  # item names; the recipe scroll is not among them


class Derived(DeclarativeBase):
    """Tables computed from the raw replay logs. `recompute` drops and rebuilds them, so their shape may change freely."""


class PlayerMinute(Derived):
    __tablename__ = "player_minute"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    player_slot: Mapped[int] = mapped_column(primary_key=True)
    minute: Mapped[int] = mapped_column(primary_key=True)
    gold: Mapped[int]  # total earned, not what is in the bank
    xp: Mapped[int]
    net_worth: Mapped[int]
    last_hits: Mapped[int]
    denies: Mapped[int]
    hero_damage: Mapped[int]  # dealt to enemy heroes, as the replay counts it
    damage_taken: Mapped[int]  # from enemy heroes, added up from the combat log
    healing: Mapped[int]  # of the other heroes on the own team; what a hero heals itself is not counted
    camps_stacked: Mapped[int]  # so far, like every column here
    camps_pulled: Mapped[int]  # into the own lane creeps; worked out from creep deaths, see derive.pulls
    lotuses: Mapped[int]  # collected from the pools; worked out from the positions, see derive.lotuses
    twin_gates: Mapped[int]  # trips through a twin gate, see derive.twin_gates


class Purchase(Derived):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(index=True)
    player_slot: Mapped[int]
    time: Mapped[int]  # game clock in seconds, negative before the horn
    item: Mapped[str]  # without the item_ prefix, like Item.name
    built_at: Mapped[int | None]  # when it became part of a bigger item; None while it is an item of its own


class Death(Derived):
    __tablename__ = "deaths"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(index=True)
    player_slot: Mapped[int]
    time: Mapped[int]
    x: Mapped[float | None]
    y: Mapped[float | None]
    killer_slot: Mapped[int | None]  # None when not killed by a hero
    in_teamfight: Mapped[bool]


class Teamfight(Derived):
    __tablename__ = "teamfights"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    n: Mapped[int] = mapped_column(primary_key=True)
    start: Mapped[int]
    end: Mapped[int]
    deaths: Mapped[int]


class TeamfightPlayer(Derived):
    __tablename__ = "teamfight_players"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    n: Mapped[int] = mapped_column(primary_key=True)
    player_slot: Mapped[int] = mapped_column(primary_key=True)
    took_part: Mapped[bool]
    damage: Mapped[int]  # dealt to enemy heroes
    healing: Mapped[int]  # of the other heroes on the own team
    deaths: Mapped[int]
    net_worth_gain: Mapped[int]  # from the fight's start to its end; a death or a buyback can make it negative
    xp_gain: Mapped[int]


class Ward(Derived):
    __tablename__ = "wards"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(index=True)
    player_slot: Mapped[int]
    type: Mapped[str]  # obs | sen
    x: Mapped[float]
    y: Mapped[float]
    placed: Mapped[int]
    removed: Mapped[int | None]  # None when still standing at the end
    killed: Mapped[bool]
    killed_by: Mapped[int | None]  # None when it expired, or a creep did it


class AbilityUpgrade(Derived):
    """A skill point spent, on an ability or on a talent."""

    __tablename__ = "ability_upgrades"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(index=True)
    player_slot: Mapped[int]
    time: Mapped[int]
    ability: Mapped[str]  # like Ability.name
    level: Mapped[int]  # of the ability, after the point
    hero_level: Mapped[int | None]  # of the hero at that second


class Building(Derived):
    """A tower, a barracks or an Ancient that fell. A building without a row stood to the end."""

    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str]  # goodguys_tower1_mid; the two tier-4 towers of a side share goodguys_tower4
    time: Mapped[int]


class Lane(Derived):
    __tablename__ = "lanes"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    player_slot: Mapped[int] = mapped_column(primary_key=True)
    lane: Mapped[str | None]  # top | mid | bot | jungle; None when the player never left the base


class Tormentor(Derived):
    """A Tormentor killed."""

    __tablename__ = "tormentors"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(index=True)
    time: Mapped[int]
    radiant: Mapped[bool]  # the side that killed it
    enemies_dead: Mapped[int]  # heroes of the other side dead at that second
    radiant_lead: Mapped[int]  # Radiant's net worth minus Dire's at that second


class WisdomRune(Derived):
    """A wisdom rune that appeared, and who came for it; see derive.wisdom_runes."""

    __tablename__ = "wisdom_runes"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    time: Mapped[int] = mapped_column(primary_key=True)  # when it appeared: 420, 840, ...
    rune: Mapped[str] = mapped_column(primary_key=True)  # radiant | dire: the half of the map it is in
    radiant_heroes: Mapped[int]
    dire_heroes: Mapped[int]
    radiant_deaths: Mapped[int]  # heroes of each side that died at it, see derive.wisdom_runes
    dire_deaths: Mapped[int]
    taken_by_radiant: Mapped[bool | None]  # None when nobody took it before the next one appeared
    radiant_lead: Mapped[int]  # Radiant's net worth minus Dire's when it appeared


class Metric(Derived):
    __tablename__ = "metrics"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    player_slot: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(primary_key=True)  # a function in metrics.py
    value: Mapped[float]  # a metric that does not apply to a player has no row


TABLES = (
    PlayerMinute, Purchase, AbilityUpgrade, Death, Teamfight, TeamfightPlayer, Ward, Building, Lane, Tormentor, WisdomRune, Metric,
)  # fmt: skip


def open_engine() -> Engine:
    DATA.mkdir(exist_ok=True)
    engine = create_engine(f"sqlite:///{DATA / 'dotanalyst.db'}")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    with engine.begin() as c:  # create_all adds no columns to a table that exists
        if "avatar" not in {col["name"] for col in inspect(c).get_columns("accounts")}:
            c.exec_driver_sql("ALTER TABLE accounts ADD COLUMN avatar VARCHAR")
        if "replays_wanted" not in {col["name"] for col in inspect(c).get_columns("player_game_lists")}:
            c.exec_driver_sql("ALTER TABLE player_game_lists ADD COLUMN replays_wanted BOOLEAN NOT NULL DEFAULT 0")
        if "twin_gates" not in {col["name"] for col in inspect(c).get_columns("player_minute")}:  # 0 until recompute
            c.exec_driver_sql("ALTER TABLE player_minute ADD COLUMN twin_gates INTEGER NOT NULL DEFAULT 0")
    return engine


def open_session() -> Session:
    return Session(open_engine())
