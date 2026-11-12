"""Custom metrics, one per function.

Each takes a match (the dict `queries.match` returns: scoreboard plus replay stats) and a player slot, and returns a
number, or None where the metric does not apply. To add one: write the function, add it to METRICS, test it on the
fixture replay, give it a label in the frontend, and run `recompute`.
"""
from statistics import mean


def _at_ten(match: dict, slot: int | None) -> dict | None:
    return next((r for r in match["player_minute"] if r["player_slot"] == slot and r["minute"] == 10), None)


def _lane_diff(match: dict, slot: int, stat: str) -> int | None:
    opponent = next((lane["opponent_slot"] for lane in match["lanes"] if lane["player_slot"] == slot), None)
    mine, theirs = _at_ten(match, slot), _at_ten(match, opponent)
    return None if mine is None or theirs is None else mine[stat] - theirs[stat]


def lane_cs_diff(match: dict, slot: int) -> int | None:
    """Own last hits at 10:00 minus the lane opponent's."""
    return _lane_diff(match, slot, "last_hits")


def lane_nw_diff(match: dict, slot: int) -> int | None:
    """Own net worth at 10:00 minus the lane opponent's."""
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
