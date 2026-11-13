"""Stats computed from a match's raw replay log. Everything here can be thrown away and rebuilt with `recompute`."""
import gzip
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from . import queries
from .db import (
    DATA, TABLES, Death, Derived, Lane, Match, Metric, PlayerMinute, Purchase, Recipe, Teamfight, TeamfightPlayer,
    Ward,
)  # fmt: skip
from .metrics import METRICS

USED = {
    "interval", "player_slot", "death_tick", "obs", "sen", "obs_left", "sen_left",
    "DOTA_COMBATLOG_DEATH", "DOTA_COMBATLOG_DAMAGE", "DOTA_COMBATLOG_HEAL", "DOTA_COMBATLOG_PURCHASE",
    "DOTA_COMBATLOG_ITEM",
}  # fmt: skip
# a combined lotus counts as the lotuses it was made from
LOTUSES = {"item_famango": 1, "item_great_famango": 3, "item_greater_famango": 6}
TREADS_STAT = {"belt_of_strength", "boots_of_elves", "robe"}
FIGHT_GAP = 15  # seconds without a death that end a fight; also how long before the first death it starts
FIGHT_DEATHS = 3
LANING_END = 600


def read_log(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as lines:
        return [event for event in map(json.loads, lines) if event["type"] in USED]


class Log:
    """The events of one match plus the lookups every derivation needs. `slot` is the replay's 0-9 player index."""

    def __init__(self, events: list[dict]):
        self.events = events
        self.player_slot: dict[int, int] = {}  # slot -> player_slot (0-4 Radiant, 128-132 Dire)
        self.hero_slot: dict[str, int] = {}  # combat log name -> slot
        self.at: dict[tuple[int, int], dict] = {}  # (time, slot) -> that second's interval
        self.end = 0
        for e in events:
            if e["type"] == "player_slot":
                self.player_slot[int(e["key"])] = e["value"]
            elif e["type"] == "interval":
                self.at[e["time"], e["slot"]] = e
                self.end = max(self.end, e["time"])
                if e.get("hero_id") and e.get("unit"):
                    # CDOTA_Unit_Hero_ShadowDemon is npc_dota_hero_shadowdemon or npc_dota_hero_shadow_demon
                    # in the combat log, depending on the hero; register both spellings
                    name = e["unit"].removeprefix("CDOTA_Unit_Hero_")
                    self.hero_slot["npc_dota_hero_" + name.lower()] = e["slot"]
                    self.hero_slot["npc_dota_hero" + "".join("_" + c.lower() if c.isupper() else c for c in name)] = (
                        e["slot"]
                    )

    def radiant(self, slot: int) -> bool:
        return self.player_slot[slot] < 128

    def hero_hits(self):
        """(time, attacker slot, victim slot, damage) for each hit by a hero on an enemy hero."""
        for e in self.events:
            if e["type"] == "DOTA_COMBATLOG_DAMAGE" and e.get("targethero") and not e.get("targetillusion"):
                attacker, victim = self.hero_slot.get(e.get("sourcename")), self.hero_slot.get(e.get("targetname"))
                if attacker is not None and victim is not None and self.radiant(attacker) != self.radiant(victim):
                    yield e["time"], attacker, victim, e["value"]

    def hero_heals(self):
        """(time, healer slot, amount) for each heal by a hero on a hero of its own team, itself included."""
        for e in self.events:
            if e["type"] == "DOTA_COMBATLOG_HEAL" and e.get("targethero") and not e.get("targetillusion"):
                healer, healed = self.hero_slot.get(e.get("sourcename")), self.hero_slot.get(e.get("targetname"))
                if healer is not None and healed is not None and self.radiant(healer) == self.radiant(healed):
                    yield e["time"], healer, e["value"]


def minutes(log: Log) -> list[dict]:
    eaten = [
        (e["time"], log.hero_slot[e["attackername"]], LOTUSES[e["inflictor"]])
        for e in log.events
        if e["type"] == "DOTA_COMBATLOG_ITEM" and e.get("inflictor") in LOTUSES and e.get("attackername") in log.hero_slot
    ]
    rows = []
    for slot, player_slot in sorted(log.player_slot.items()):
        for minute in range(log.end // 60 + 1):
            e = log.at.get((minute * 60, slot))
            if e:
                rows.append(
                    {
                        "player_slot": player_slot, "minute": minute, "gold": e["gold"], "xp": e["xp"],
                        "net_worth": e["networth"], "last_hits": e["lh"], "denies": e["denies"],
                        "camps_stacked": e.get("camps_stacked", 0),
                        "lotuses": sum(n for time, who, n in eaten if who == slot and time <= minute * 60),
                    }  # fmt: skip
                )
    return rows


def purchases(log: Log, recipes: dict[str, list[str]]) -> list[dict]:
    """Every purchase. The log reports a finished item as a purchase too, at the moment its parts come together;
    `recipes` (item -> components) then tells which earlier purchases it used up."""
    rows = [
        {
            "player_slot": log.player_slot[log.hero_slot[e["targetname"]]],
            "time": e["time"],
            "item": e["valuename"].removeprefix("item_"),
            "built_at": None,
        }
        for e in log.events
        if e["type"] == "DOTA_COMBATLOG_PURCHASE" and e.get("targetname") in log.hero_slot and e.get("valuename")
    ]
    for built in rows:
        for component in recipes.get(built["item"], ()):
            # the recipe list names one of the three items Power Treads can be built with
            wanted = TREADS_STAT if built["item"] == "power_treads" and component in TREADS_STAT else {component}
            parts = [
                r for r in rows
                if r is not built and r["player_slot"] == built["player_slot"] and r["item"] in wanted
                and r["built_at"] is None and r["time"] <= built["time"]
            ]  # fmt: skip
            if parts:  # none when an ally bought the part
                max(parts, key=lambda r: r["time"])["built_at"] = built["time"]
    return rows


def fights(death_times: list[int]) -> list[tuple[int, int, int]]:
    """(start, end, deaths) of each teamfight: deaths less than FIGHT_GAP apart, at least FIGHT_DEATHS of them."""
    groups: list[list[int]] = []  # [first death, last death, count]
    for time in sorted(death_times):
        if groups and time - groups[-1][1] < FIGHT_GAP:
            groups[-1][1] = time
            groups[-1][2] += 1
        else:
            groups.append([time, time, 1])
    return [(first - FIGHT_GAP, last + FIGHT_GAP, count) for first, last, count in groups if count >= FIGHT_DEATHS]


def deaths(log: Log) -> list[dict]:
    """One row per scoreboard death. The combat log also reports deaths that do not count (Aegis, reincarnation,
    clones), so it only supplies the killer."""
    killers = {}
    for e in log.events:
        if e["type"] == "DOTA_COMBATLOG_DEATH" and e.get("targetname") in log.hero_slot:
            killers[e["time"], log.hero_slot[e["targetname"]]] = log.hero_slot.get(e.get("sourcename"))
    ticks = [e for e in log.events if e["type"] == "death_tick" and e["slot"] in log.player_slot]
    windows = fights([e["time"] for e in ticks])
    rows = []
    for e in ticks:
        time, slot = e["time"], e["slot"]
        where = log.at.get((time, slot), {})
        # the two streams can land on neighbouring seconds
        killer = next((killers[t, slot] for t in (time, time - 1, time + 1) if (t, slot) in killers), None)
        rows.append(
            {
                "player_slot": log.player_slot[slot], "time": time, "x": where.get("x"), "y": where.get("y"),
                "killer_slot": None if killer is None else log.player_slot[killer],
                "in_teamfight": any(start <= time <= end for start, end, _ in windows),
            }  # fmt: skip
        )
    return rows


def teamfights(log: Log, death_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fights, and for each fight one row per player. A player took part by trading damage with an enemy hero or dying."""
    hits, heals = list(log.hero_hits()), list(log.hero_heals())
    fight_rows, player_rows = [], []
    for n, (start, end, count) in enumerate(fights([d["time"] for d in death_rows])):
        fight_rows.append({"n": n, "start": start, "end": end, "deaths": count})
        dealt, healed, involved = Counter(), Counter(), set()
        for time, attacker, victim, damage in hits:
            if start <= time <= end:
                dealt[attacker] += damage
                involved |= {attacker, victim}
        for time, healer, amount in heals:
            if start <= time <= end:
                healed[healer] += amount
        died = Counter(d["player_slot"] for d in death_rows if start <= d["time"] <= end)
        for slot, player_slot in sorted(log.player_slot.items()):
            # the window can reach past the last second of the game
            before, after = log.at.get((start, slot)), log.at.get((min(end, log.end), slot))
            player_rows.append(
                {
                    "n": n, "player_slot": player_slot, "damage": dealt[slot], "healing": healed[slot],
                    "deaths": died[player_slot], "took_part": slot in involved or died[player_slot] > 0,
                    "net_worth_gain": after["networth"] - before["networth"] if before and after else 0,
                    "xp_gain": after["xp"] - before["xp"] if before and after else 0,
                }  # fmt: skip
            )
    return fight_rows, player_rows


def wards(log: Log) -> list[dict]:
    rows = []
    standing = {}  # (type, ehandle) -> its row; an entity handle is reused once the ward is gone
    for e in log.events:
        kind = e["type"][:3]
        if e["type"] in ("obs", "sen") and e.get("slot") in log.player_slot:
            row = {
                "player_slot": log.player_slot[e["slot"]], "type": kind, "x": e["x"], "y": e["y"],
                "placed": e["time"], "removed": None, "killed": False, "killed_by": None,
            }  # fmt: skip
            rows.append(row)
            standing[kind, e["ehandle"]] = row
        elif e["type"] in ("obs_left", "sen_left") and (kind, e["ehandle"]) in standing:
            row = standing.pop((kind, e["ehandle"]))
            row["removed"] = e["time"]
            # a ward that runs out is reported with one of the owner's team as attacker
            attacker = log.hero_slot.get(e.get("attackername"))
            owner_is_radiant = row["player_slot"] < 128
            if attacker is None:
                row["killed"] = bool(e.get("attackername"))  # a creep or a building
            elif log.radiant(attacker) != owner_is_radiant:
                row["killed"], row["killed_by"] = True, log.player_slot[attacker]
    return rows


def zone(x: float, y: float) -> str | None:
    """Part of the map a position belongs to. Coordinates are replay cells: about 64-191, Radiant base bottom left."""
    if (x < 96 and y < 96) or (x > 160 and y > 160):
        return None  # a base says nothing about the lane
    if abs(x - y) < 14:
        return "mid"
    if y > x:
        return "top" if x < 96 or y > 160 else "jungle"
    return "bot" if y < 96 or x > 160 else "jungle"


def lanes(log: Log) -> list[dict]:
    """Lane = where the player spent most of the first ten minutes."""
    votes = {slot: Counter() for slot in log.player_slot}
    for (time, slot), e in log.at.items():
        if 0 <= time <= LANING_END and e.get("x") is not None and slot in votes:
            votes[slot][zone(e["x"], e["y"])] += 1
    rows = []
    for slot, player_slot in sorted(log.player_slot.items()):
        del votes[slot][None]
        rows.append({"player_slot": player_slot, "lane": votes[slot].most_common(1)[0][0] if votes[slot] else None})
    return rows


def derive(events: list[dict], recipes: dict[str, list[str]] | None = None) -> dict[type, list[dict]]:
    log = Log(events)
    death_rows = deaths(log)
    fight_rows, fight_player_rows = teamfights(log, death_rows)
    return {
        PlayerMinute: minutes(log),
        Purchase: purchases(log, recipes or {}),
        Death: death_rows,
        Teamfight: fight_rows,
        TeamfightPlayer: fight_player_rows,
        Ward: wards(log),
        Lane: lanes(log),
    }


def derive_match(session: Session, match_id: int, raw_dir: Path = DATA / "raw") -> None:
    """Replace one match's derived rows."""
    recipes = {r.item: r.components for r in session.scalars(select(Recipe))}
    rows = derive(read_log(raw_dir / f"{match_id}.jsonl.gz"), recipes)
    for model in TABLES:
        session.execute(delete(model).where(model.match_id == match_id))
        if rows.get(model):
            session.execute(insert(model), [{"match_id": match_id, **row} for row in rows[model]])
    # metrics read the rows just written, together with the scoreboard, in the shape the API serves
    match = queries.match(session, match_id)
    values = [
        {"match_id": match_id, "player_slot": lane["player_slot"], "name": metric.__name__, "value": value}
        for lane in match["lanes"]
        for metric in METRICS
        if (value := metric(match, lane["player_slot"])) is not None
    ]
    if values:
        session.execute(insert(Metric), values)
    session.commit()


def recompute(session: Session, raw_dir: Path = DATA / "raw") -> tuple[int, list[str]]:
    """Rebuild every derived table from the raw logs. Returns (matches done, what went wrong)."""
    bind = session.get_bind()
    Derived.metadata.drop_all(bind)
    Derived.metadata.create_all(bind)
    done, problems = 0, []
    for match_id in session.scalars(select(Match.match_id).where(Match.replay_state == "parsed")).all():
        try:
            derive_match(session, match_id, raw_dir)
            done += 1
        except (OSError, ValueError, KeyError) as error:  # a missing or damaged log must not stop the rest
            session.rollback()
            problems.append(f"match {match_id}: {error!r}")
    return done, problems
