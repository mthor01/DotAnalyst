"""Custom metrics, one per function.

Each takes a match (the dict `queries.match` returns: scoreboard plus replay stats) and a player slot, and returns a
number, or None where the metric does not apply. To add one: write the function, add it to METRICS, test it on the
fixture replay, give it a label in the frontend, and run `recompute`.
"""
from statistics import mean


def _ten(match: dict, slot: int, stat: str) -> int | None:
    """The player's `stat` at 10:00; None in a match that ended before."""
    return next((r[stat] for r in match["player_minute"] if r["minute"] == 10 and r["player_slot"] == slot), None)


def _lane_sides(match: dict, slot: int, stat: str) -> tuple[int, int] | None:
    """`stat` at 10:00 summed over the player's side of their lane, and over the enemies in that lane. None outside
    the three lanes, with nobody to compare with, or in a match that ended before 10:00."""
    lane = next((row["lane"] for row in match["lanes"] if row["player_slot"] == slot), None)
    if lane not in ("top", "mid", "bot"):
        return None
    ten = {r["player_slot"]: r[stat] for r in match["player_minute"] if r["minute"] == 10}
    there = [row["player_slot"] for row in match["lanes"] if row["lane"] == lane and row["player_slot"] in ten]
    mine = [ten[s] for s in there if (s < 128) == (slot < 128)]
    theirs = [ten[s] for s in there if (s < 128) != (slot < 128)]
    return (sum(mine), sum(theirs)) if mine and theirs else None


def _lane_diff(match: dict, slot: int, stat: str) -> int | None:
    """The player's side of their lane at 10:00 minus the enemies in that lane, see _lane_sides."""
    sides = _lane_sides(match, slot, stat)
    return sides and sides[0] - sides[1]


def lane_cs_diff(match: dict, slot: int) -> int | None:
    """Last hits of the player's lane at 10:00 minus the enemy lane's."""
    return _lane_diff(match, slot, "last_hits")


def lane_nw_diff(match: dict, slot: int) -> int | None:
    """Net worth of the player's lane at 10:00 minus the enemy lane's."""
    return _lane_diff(match, slot, "net_worth")


def last_hits_at_10(match: dict, slot: int) -> int | None:
    return _ten(match, slot, "last_hits")


def denies_at_10(match: dict, slot: int) -> int | None:
    return _ten(match, slot, "denies")


def net_worth_at_10(match: dict, slot: int) -> int | None:
    return _ten(match, slot, "net_worth")


def xp_at_10(match: dict, slot: int) -> int | None:
    return _ten(match, slot, "xp")


def damage_at_10(match: dict, slot: int) -> int | None:
    """Damage the player dealt to enemy heroes by 10:00."""
    return _ten(match, slot, "hero_damage")


def damage_taken_at_10(match: dict, slot: int) -> int | None:
    """Damage the player took from enemy heroes by 10:00, whichever lane they came from."""
    return _ten(match, slot, "damage_taken")


def lane_damage_at_10(match: dict, slot: int) -> int | None:
    """Damage to enemy heroes by 10:00 of the player's side of their lane: the player and their lane partners."""
    sides = _lane_sides(match, slot, "hero_damage")
    return sides and sides[0]


def enemy_lane_damage_at_10(match: dict, slot: int) -> int | None:
    """Damage the enemies in the player's lane dealt by 10:00, to any hero of the player's side."""
    sides = _lane_sides(match, slot, "hero_damage")
    return sides and sides[1]


def _last(match: dict, slot: int, stat: str) -> int | None:
    """The player's `stat` at the last whole minute of the match."""
    mine = [r for r in match["player_minute"] if r["player_slot"] == slot]
    return max(mine, key=lambda r: r["minute"])[stat] if mine else None


def camps_stacked(match: dict, slot: int) -> int | None:
    """Camps the player stacked in the whole match, as the replay counts them up to its last whole minute."""
    return _last(match, slot, "camps_stacked")


def camps_pulled_by_10(match: dict, slot: int) -> int | None:
    return _ten(match, slot, "camps_pulled")


def kills_by_10(match: dict, slot: int) -> int | None:
    """Heroes the player killed before 10:00 (the last hit, not assists)."""
    if _ten(match, slot, "xp") is None:
        return None
    return sum(d["killer_slot"] == slot and d["time"] < 600 for d in match["deaths"])


def deaths_by_10(match: dict, slot: int) -> int | None:
    if _ten(match, slot, "xp") is None:
        return None
    return sum(d["player_slot"] == slot and d["time"] < 600 for d in match["deaths"])


def obs_placed(match: dict, slot: int) -> int:
    return sum(w["player_slot"] == slot and w["type"] == "obs" for w in match["wards"])


def sen_placed(match: dict, slot: int) -> int:
    return sum(w["player_slot"] == slot and w["type"] == "sen" for w in match["wards"])


def obs_bought(match: dict, slot: int) -> int:
    """Observers bought. A ward_dispenser purchase is the game merging or splitting wards already bought, so it is not
    counted."""
    return sum(p["player_slot"] == slot and p["item"] == "ward_observer" for p in match["purchases"])


def sen_bought(match: dict, slot: int) -> int:
    return sum(p["player_slot"] == slot and p["item"] == "ward_sentry" for p in match["purchases"])


def wards_destroyed(match: dict, slot: int) -> int:
    """Enemy wards of either kind this player destroyed."""
    return sum(w["killed_by"] == slot for w in match["wards"])


def obs_lifetime(match: dict, slot: int) -> float | None:
    """Mean seconds this player's observers stood. One still standing at the end has no lifetime yet and is left out."""
    lives = [
        w["removed"] - w["placed"]
        for w in match["wards"]
        if w["player_slot"] == slot and w["type"] == "obs" and w["removed"] is not None
    ]
    return mean(lives) if lives else None


def fight_participation(match: dict, slot: int) -> float | None:
    """Share (0-1) of the match's teamfights the player took part in."""
    mine = [p["took_part"] for p in match["teamfight_players"] if p["player_slot"] == slot]
    return mean(mine) if mine else None


def kill_participation(match: dict, slot: int) -> float | None:
    """(kills + assists) / team kills, from the scoreboard."""
    team = [p for p in match["players"] if (p["player_slot"] < 128) == (slot < 128)]
    me = next((p for p in team if p["player_slot"] == slot), None)
    team_kills = sum(p["kills"] or 0 for p in team)
    return None if me is None or not team_kills else ((me["kills"] or 0) + (me["assists"] or 0)) / team_kills


def deaths_outside_fights(match: dict, slot: int) -> int:
    return sum(d["player_slot"] == slot and not d["in_teamfight"] for d in match["deaths"])


METRICS = (
    lane_cs_diff, lane_nw_diff, last_hits_at_10, denies_at_10, net_worth_at_10, xp_at_10, damage_at_10,
    damage_taken_at_10, lane_damage_at_10, enemy_lane_damage_at_10, kills_by_10, deaths_by_10, camps_pulled_by_10,
    camps_stacked, obs_placed, sen_placed, obs_bought, sen_bought, wards_destroyed, obs_lifetime,
    fight_participation, kill_participation, deaths_outside_fights,
)  # fmt: skip
NAMES = tuple(metric.__name__ for metric in METRICS)
