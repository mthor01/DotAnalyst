"""Liquipedia's page source read into brackets, groups, upcoming matches and rosters (invented fixtures)."""
import calendar
from pathlib import Path

import pytest

from dotanalyst import lp_structure as lp

FIXTURES = Path(__file__).parent / "fixtures"
EVENT = (FIXTURES / "lp_event.txt").read_text()
LAYOUT = lp.layout((FIXTURES / "lp_layout.txt").read_text())
NOV_20 = calendar.timegm((2026, 11, 20, 0, 0, 0))


@pytest.fixture
def found():
    return lp.structure({"Pro Series 5": EVENT}, {"Bracket/4DE": LAYOUT}, NOV_20)


def names(m: dict) -> list:
    return [o["name"] if isinstance(o, dict) else o for o in m["opponents"]]


def test_params_respect_nested_braces():
    p = lp.params("Match|date=X {{Abbr/CET}}|map1={{Map|winner=1}}|a=b|[[Link|text]]")
    assert set(p) == {"date", "map1", "a", "1"}
    assert p["date"] == "X {{Abbr/CET}}" and p["map1"] == "{{Map|winner=1}}" and p["1"] == "[[Link|text]]"


def test_when_reads_the_zone():
    assert lp.when("November 13, 2026 - 11:00 {{Abbr/CET}}") == calendar.timegm((2026, 11, 13, 10, 0, 0))
    assert lp.when("November 13, 2026 - 11:00 {{Abbr/XYZ}}") == calendar.timegm((2026, 11, 13, 11, 0, 0))
    assert lp.when("November 13, 2026") == calendar.timegm((2026, 11, 13, 12, 0, 0))
    assert lp.when("TBA") is None


def test_match_reads_teams_date_ids_and_score():
    (_, body), *_ = lp.blocks(EVENT, "Match")
    m = lp.match(body)
    assert m["opponents"] == ["Team A", "Team B"] and m["match_ids"] == [9001, 9002]
    assert m["score"] == [2, 0] and m["winner"] == 0 and len(m["maps"]) == 2
    assert m["time"] == calendar.timegm((2026, 11, 13, 10, 0, 0))


def test_layout_sections_and_feeders():
    by_id = {s["id"]: s for s in LAYOUT}
    assert {i for i, s in by_id.items() if s["section"] == "lower"} == {"R02-M002", "R03-M001"}
    assert by_id["R04-M001"]["root"] and (by_id["R04-M001"]["toupper"], by_id["R04-M001"]["tolower"]) == ("R02-M001", "R03-M001")


def test_round_names_page_header_beats_code_and_unknown_code(found):
    (playoffs,) = found["brackets"]
    assert playoffs["title"] == "Playoffs"
    upper, lower = playoffs["sections"]
    assert [r["name"] for r in upper["rounds"]] == ["Semifinals", "Upper Bracket Final", "Round 4"]  # no reset played
    assert [r["name"] for r in lower["rounds"]] == ["Lower Bracket Round 1", "Lower Bracket Final"]
    final = upper["rounds"][2]["matches"][0]
    assert final["id"] == "R04-M001" and final["feeders"] == ["R02-M001", "R03-M001"]
    assert upper["rounds"][0]["matches"][1]["winner"] == 1  # Team Z beat Team C


def test_tbd_matches_parse_and_are_not_upcoming(found):
    upper, lower = found["brackets"][0]["sections"]
    assert names(upper["rounds"][2]["matches"][0]) == [None, None] and names(lower["rounds"][1]["matches"][0]) == [None, None]
    assert all(None not in names(m) for m in found["upcoming"])


def test_group_standings_from_same_page_matchlists(found):
    (group,) = found["groups"]
    assert group["title"] == "Group A"
    rows = [(r["name"], r["series_wins"], r["series_losses"], r["map_wins"], r["map_losses"]) for r in group["rows"]]
    assert rows == [("Team A", 1, 0, 2, 0), ("Team B", 1, 1, 2, 3), ("Team C", 0, 1, 1, 2)]  # playoff games left out


def test_upcoming_soonest_first_and_not_stale(found):
    assert [names(m) for m in found["upcoming"]] == [["Team A", "Team C"], ["Team A", "Team Z"]]
    later = lp.structure({"Pro Series 5": EVENT}, {"Bracket/4DE": LAYOUT}, calendar.timegm((2026, 12, 2, 0, 0, 0)))
    assert later["upcoming"] == []


def test_rosters(found):
    assert found["rosters"] == [{"name": "Team A", "players": [
        {"handle": "Player 1", "role": "1", "sub": False}, {"handle": "Player 2", "role": "5", "sub": True}]}]  # fmt: skip


def test_identify_by_match_id_then_name(found):
    games = [{"match_id": 9001, "radiant": {"team_id": 3001}, "dire": {"team_id": 3002}}]
    lp.identify(found, games, [{"team_id": 3003, "name": "team c"}])
    first = found["brackets"][0]["sections"][0]["rounds"][0]["matches"]
    assert [o["team_id"] for o in first[0]["opponents"]] == [3001, 3002]  # by match 9001: Team A was Radiant
    assert [o["team_id"] for o in first[1]["opponents"]] == [3003, 0]  # Team C by name, Team Z unknown
    assert found["rosters"][0]["team_id"] == 3001 and found["groups"][0]["rows"][2]["team_id"] == 3003


def test_layout_names():
    assert lp.layout_names({"x": EVENT}) == {"Bracket/4DE"}


def test_group_members_match_their_matches_in_any_case():
    pool = [{"opponents": ["Team A", "TEAM B"], "score": [2, 1]}]
    rows = lp.group_rows(["team a", "Team B"], pool)
    assert [(r["name"], r["series_wins"]) for r in rows] == [("team a", 1), ("Team B", 0)]
