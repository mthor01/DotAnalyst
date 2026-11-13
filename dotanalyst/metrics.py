"""Custom metrics, one per function.

Each takes a match (the dict `queries.match` returns: scoreboard plus replay stats) and a player slot, and returns a
number, or None where the metric does not apply. To add one: write the function, add it to METRICS, test it on the
fixture replay, give it a label in the frontend, and run `recompute`.
"""
from statistics import mean


def _lane_diff(match: dict, slot: int, stat: str) -> int | None:
    """The player's side of their lane, summed at 10:00, minus the enemies in that lane. None outside the three lanes,
    with nobody to compare with, or in a match that ended before 10:00."""
    lane = next((row["lane"] for row in match["lanes"] if row["player_slot"] == slot), None)
    if lane not in ("top", "mid", "bot"):
        return None
    ten = {r["player_slot"]: r[stat] for r in match["player_minute"] if r["minute"] == 10}
    there = [row["player_slot"] for row in match["lanes"] if row["lane"] == lane and row["player_slot"] in ten]
    mine = [ten[s] for s in there if (s < 128) == (slot < 128)]
    theirs = [ten[s] for s in there if (s < 128) != (slot < 128)]
    return sum(mine) - sum(theirs) if mine and theirs else None


def lane_cs_diff(match: dict, slot: int) -> int | None:
    """Last hits of the player's lane at 10:00 minus the enemy lane's."""
    return _lane_diff(match, slot, "last_hits")


def lane_nw_diff(match: dict, slot: int) -> int | None:
    """Net worth of the player's lane at 10:00 minus the enemy lane's."""
    return _lane_diff(match, slot, "net_worth")


def obs_placed(match: dict, slot: int) -> int:
    return sum(w["player_slot"] == slot and w["type"] == "obs" for w in match["wards"])


def sen_placed(match: dict, slot: int) -> int:
    return sum(w["player_slot"] == slot and w["type"] == "sen" for w in match["wards"])


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
    lane_cs_diff, lane_nw_diff, obs_placed, sen_placed, wards_destroyed, obs_lifetime,
    fight_participation, kill_participation, deaths_outside_fights,
)  # fmt: skip
NAMES = tuple(metric.__name__ for metric in METRICS)
