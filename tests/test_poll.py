import bz2
import gzip
import json
import os
import subprocess
import time
from compression import zstd
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dotanalyst.db import (Account, Base, Derived, League, LeagueMatch, Match, MatchPlayer, PlayerGame, PlayerGameList, PlayerMinute, PlayerName,)  # fmt: skip
from dotanalyst import poll
from dotanalyst.poll import RETRY_SECONDS, poll_once, request_replay
from dotanalyst.replay import ReplayError, replay_complete
from dotanalyst.steam import store_league_match

FIXTURES = Path(__file__).parent / "fixtures"
GOOD = 8810606282
LOG = gzip.decompress((FIXTURES / f"{GOOD}.jsonl.gz").read_bytes())
OPENDOTA = (FIXTURES / "opendota_match.json").read_bytes()  # a real response; its replay_salt is 519105714
WRONG_LOG, STILL_DOWNLOADING, NOT_STORED = 11, 22, 33
# the smallest whole replay: magic, the offset of the file info record (16), 4 bytes, then the record itself:
# kind 0x42, tick 0, a body of 3 bytes
REPLAY = b"PBDEMS2\0" + (16).to_bytes(4, "little") + bytes(4) + bytes([0x42, 0, 3]) + b"abc"
CLUSTER = 444
DAY = 86400


def add_match(session: Session, match_id: int, age_days: float = 0) -> None:
    session.add(
        Match(
            match_id=match_id, match_seq_num=match_id, start_time=int(time.time() - age_days * DAY), duration=1,
            radiant_win=True, game_mode=22, lobby_type=7, cluster=CLUSTER, raw_json={},
        )
    )
    session.commit()


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Derived.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def network(calls: list[str], opendota=(404, b""), valve=(404, b"")) -> httpx.Client:
    """OpenDota, Valve's replay servers and the parser; the parser always returns the log of GOOD."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "api.opendota.com":
            return httpx.Response(opendota[0], content=opendota[1])
        if request.url.host.endswith(".valve.net"):
            return httpx.Response(valve[0], content=valve[1])
        assert request.url.host == "localhost"
        assert request.content == REPLAY  # the parser gets the decompressed file
        return httpx.Response(200, content=LOG)

    return httpx.Client(transport=httpx.MockTransport(handler))


def to(host: str, calls: list[str]) -> list[str]:
    return [url for url in calls if host in url]


def for_replays(calls: list[str]) -> list[str]:
    """Leaves out the lists of the league players' own games, which test_opendota covers."""
    return [url for url in calls if "/players/" not in url]


def test_a_server_error_stops_the_downloads_left_until_the_next_poll(session, tmp_path):
    for match_id in range(1, 21):
        add_match(session, match_id)
    poll.STEPS.clear()

    poll_once(session, network([], opendota=(200, OPENDOTA), valve=(500, b"")), "", tmp_path / "nowhere", tmp_path)
    assert "; then stopped: HTTPStatusError" in poll.STEPS["downloads"]["what"]
    assert any("download stopped, the rest waits for the next poll" in e["message"] for e in poll.EVENTS)
    # none is lost: whether it ran or was cancelled, each stays wanted
    assert {session.get(Match, i).replay_state for i in range(1, 21)} <= {"none", "pending"}


def test_poll_parses_downloaded_replays_of_stored_matches(session, tmp_path):
    for match_id in (GOOD, WRONG_LOG, STILL_DOWNLOADING):
        add_match(session, match_id)
    replays = tmp_path / "replays"
    replays.mkdir()
    for name in (GOOD, WRONG_LOG, NOT_STORED, "notes"):
        (replays / f"{name}.dem").write_bytes(REPLAY)
    (replays / f"{STILL_DOWNLOADING}.dem").write_bytes(REPLAY[:-1])  # the Dota client is still writing it
    calls = []
    client = network(calls)

    assert poll_once(session, client, "", replays, tmp_path) == (0, 1)
    assert [p.name for p in (tmp_path / "raw").iterdir()] == [f"{GOOD}.jsonl.gz"]
    assert session.get(Match, GOOD).replay_state == "parsed"
    assert session.get(Match, WRONG_LOG).replay_state == "failed"
    assert session.get(Match, STILL_DOWNLOADING).replay_state == "pending"  # no replay online either
    assert len(to("localhost", calls)) == 2  # not the unknown match, the unfinished file or the non-numeric name

    assert poll_once(session, client, "", replays, tmp_path) == (0, 0)
    assert len(to("localhost", calls)) == 2  # parsed and failed replays are not sent again

    (replays / f"{STILL_DOWNLOADING}.dem").write_bytes(REPLAY)  # the download finished
    poll_once(session, client, "", replays, tmp_path)
    assert len(to("localhost", calls)) == 3


@pytest.mark.parametrize(
    "content, whole",
    [(REPLAY, True), (REPLAY[:-1], False), (REPLAY + b"x", False), (b"PBDEMS1\0" + REPLAY[8:], False), (b"", False)],
    ids=["whole", "cut short", "longer than its header says", "not Source 2", "empty"],
)
def test_a_replay_is_whole_when_it_ends_where_its_header_says(tmp_path, content, whole):
    (tmp_path / "1.dem").write_bytes(content)
    assert replay_complete(tmp_path / "1.dem") is whole


def test_poll_survives_a_missing_replay_folder(session, tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path) == (0, 0)


def test_poll_downloads_and_parses_replays(session, tmp_path):
    add_match(session, GOOD)
    add_match(session, WRONG_LOG, age_days=1)  # the parser will return another match's log for it
    calls = []
    client = network(calls, opendota=(200, OPENDOTA), valve=(200, zstd.compress(REPLAY)))

    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path) == (0, 1)
    assert set(to("valve.net", calls)) == {  # side by side, so in either order
        f"http://replay{CLUSTER}.valve.net/570/{GOOD}_519105714.dem.bz2",
        f"http://replay{CLUSTER}.valve.net/570/{WRONG_LOG}_519105714.dem.bz2",
    } and len(to("valve.net", calls)) == 2
    assert session.get(Match, GOOD).replay_state == "parsed"
    assert session.get(Match, WRONG_LOG).replay_state == "failed"
    assert [p.name for p in (tmp_path / "raw").iterdir()] == [f"{GOOD}.jsonl.gz"]  # nothing for the failed parse
    assert list((tmp_path / "tmp").iterdir()) == []  # downloaded .dem files are deleted either way
    assert {row.match_id for row in session.query(PlayerMinute)} == {GOOD}  # stats follow the parse on their own

    calls.clear()
    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path) == (0, 0)
    assert calls == []  # parsed and failed matches are never fetched again


def test_a_requested_replay_is_fetched_whatever_the_age_of_the_match(session, tmp_path):
    add_match(session, GOOD, age_days=60)  # outside the download window: no poll would fetch it
    calls = []
    client = network(calls, opendota=(200, OPENDOTA), valve=(200, zstd.compress(REPLAY)))
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
    assert calls == [] and session.get(Match, GOOD).replay_state == "none"

    assert request_replay(session, client, GOOD, tmp_path) == "parsed"
    assert to("valve.net", calls) == [f"http://replay{CLUSTER}.valve.net/570/{GOOD}_519105714.dem.bz2"]
    assert {row.match_id for row in session.query(PlayerMinute)} == {GOOD}  # with its stats

    calls.clear()
    assert request_replay(session, client, GOOD, tmp_path) == "parsed"
    assert calls == []  # a stored replay is never fetched again
    assert request_replay(session, client, NOT_STORED, tmp_path) is None


def league_game(session: Session, match_id: int, age_days: float) -> dict:
    game = json.loads((FIXTURES / "league_details.json").read_text(encoding="utf-8"))["result"]["matches"][0]
    game.update(match_id=match_id, cluster=CLUSTER, start_time=int(time.time() - age_days * DAY))
    store_league_match(session, game)
    session.commit()
    return game


def test_poll_downloads_the_replays_of_recent_league_games(session, tmp_path):
    league_game(session, GOOD, age_days=2)  # the parser of these tests answers with the log of GOOD
    league_game(session, 1, age_days=60)  # outside the download window
    calls = []
    client = network(calls, opendota=(200, OPENDOTA), valve=(200, zstd.compress(REPLAY)))

    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path) == (0, 1)
    assert session.get(Match, GOOD).replay_state == "parsed"
    assert {row.match_id for row in session.query(PlayerMinute)} == {GOOD}  # with its stats
    assert session.get(Match, 1) is None
    assert to("valve.net", calls) == [f"http://replay{CLUSTER}.valve.net/570/{GOOD}_519105714.dem.bz2"]

    calls.clear()
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
    assert for_replays(calls) == []  # copied once, fetched once


def test_a_requested_replay_of_a_league_game_makes_it_a_match(session, tmp_path):
    game = league_game(session, GOOD, age_days=60)
    calls = []
    client = network(calls, opendota=(200, OPENDOTA), valve=(200, zstd.compress(REPLAY)))
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
    assert for_replays(calls) == [] and session.get(Match, GOOD) is None  # too old for a poll to fetch

    assert request_replay(session, client, GOOD, tmp_path) == "parsed"
    assert to("valve.net", calls) == [f"http://replay{CLUSTER}.valve.net/570/{GOOD}_519105714.dem.bz2"]
    assert session.get(Match, GOOD).start_time == game["start_time"]
    assert session.query(MatchPlayer).filter_by(match_id=GOOD).count() == 10
    assert {row.match_id for row in session.query(PlayerMinute)} == {GOOD}


def test_a_requested_replay_that_valve_no_longer_has_is_unavailable(session, tmp_path):
    add_match(session, 1, age_days=60)
    add_match(session, 2, age_days=1)
    client = network([], opendota=(200, OPENDOTA))  # a salt, but no file
    assert request_replay(session, client, 1, tmp_path) == "unavailable"
    assert request_replay(session, client, 2, tmp_path) == "pending"  # may still come


def test_match_without_a_replay_is_retried_and_given_up_after_14_days(session, tmp_path):
    recent, old, too_old = 1, 2, 3
    add_match(session, recent, age_days=13)
    add_match(session, old, age_days=15)
    add_match(session, too_old, age_days=31)  # outside the download window: never asked about
    calls = []
    client = network(calls)  # OpenDota knows neither match

    def poll() -> int:
        calls.clear()
        poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
        return len(to("opendota", calls))

    assert poll() == 2
    assert session.get(Match, recent).replay_state == "pending"
    assert session.get(Match, old).replay_state == "unavailable"
    assert session.get(Match, too_old).replay_state == "none"
    assert poll() == 0  # tried a moment ago

    for match in (session.get(Match, recent), session.get(Match, old)):
        match.replay_tried_at -= RETRY_SECONDS + 1
    session.commit()
    assert poll() == 1  # the pending one again; the unavailable one never


def test_the_queue_shows_the_order_the_poller_takes_matches_in(session, tmp_path, monkeypatch):
    def parser_down(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(poll.httpx, "get", parser_down)
    poll.EVENTS.clear()
    now = time.time()
    for match_id, age, tried in [(1, 2, None), (2, 1, None), (3, 3, now - 7200), (4, 0, now - 5), (5, 31, None)]:
        add_match(session, match_id, age_days=age)
        session.get(Match, match_id).replay_tried_at = tried
    session.get(Match, 3).replay_state = session.get(Match, 4).replay_state = "pending"
    session.commit()

    shown = poll.queue(session, tmp_path / "nowhere", tmp_path, now)
    assert [row["match_id"] for row in shown["queue"]] == [2, 1, 3, 4]  # 5 is outside the download window
    assert [row["next_try"] for row in shown["queue"]] == [now, now, now, now - 5 + poll.RETRY_SECONDS]
    assert shown["parser"] is False

    poll_once(session, network([]), "", tmp_path / "nowhere", tmp_path)  # OpenDota knows none of them
    assert sorted(e["match_id"] for e in poll.EVENTS) == [1, 2, 3]  # 4 was tried 5 seconds ago
    shown = poll.queue(session, tmp_path / "nowhere", tmp_path)
    assert shown["queue"][-1]["last"]["message"] == "no replay yet (no salt: OpenDota does not know it), now pending"


def test_a_refresh_by_hand_does_not_wait_for_the_retry(session, tmp_path):
    add_match(session, 1)
    calls = []
    client = network(calls)  # OpenDota does not know the match
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
    assert len(to("opendota", calls)) == 1  # the timed poll leaves a match tried a moment ago alone
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path, retry_seconds=0)
    assert len(to("opendota", calls)) == 2


def test_salt_is_asked_for_once_even_if_the_download_has_to_be_repeated(session, tmp_path):
    add_match(session, GOOD)
    calls = []
    client = network(calls, opendota=(200, OPENDOTA))  # a salt, but Valve has no file yet

    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
    session.get(Match, GOOD).replay_tried_at -= poll.RETRY_SECONDS + 1
    session.commit()
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)

    assert len(to("valve.net", calls)) == 2
    assert len(to("opendota", calls)) == 1
    assert session.get(Match, GOOD).replay_state == "pending"


def test_salts_come_from_the_second_steam_account_and_from_opendota_for_the_rest(session, tmp_path, monkeypatch):
    add_match(session, GOOD)
    add_match(session, WRONG_LOG, age_days=1)
    asked = []

    def node(command, **options):  # stands in for steam/salts.mjs: Valve has a salt for GOOD only
        asked.append(command[2:])
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({str(GOOD): 111}), stderr="")

    monkeypatch.setattr(subprocess, "run", node)
    calls = []
    client = network(calls, opendota=(200, OPENDOTA))  # salts, but Valve has no file yet

    poll_once(session, client, "", tmp_path / "nowhere", tmp_path, alt=True)
    assert asked == [[str(GOOD), str(WRONG_LOG)]]  # one login for all the matches of a poll
    assert set(to("valve.net", calls)) == {
        f"http://replay{CLUSTER}.valve.net/570/{GOOD}_111.dem.bz2",
        f"http://replay{CLUSTER}.valve.net/570/{WRONG_LOG}_519105714.dem.bz2",
    } and len(to("valve.net", calls)) == 2
    assert to("opendota", calls) == [f"https://api.opendota.com/api/matches/{WRONG_LOG}"]

    for match_id in (GOOD, WRONG_LOG):
        session.get(Match, match_id).replay_tried_at -= 3601
    session.commit()
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path, alt=True)
    assert asked[1:] == [[str(WRONG_LOG)]]  # the salt of GOOD was kept
    assert f"http://replay{CLUSTER}.valve.net/570/{GOOD}_111.dem.bz2" in to("valve.net", calls)[2:]


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CompletedProcess([], 1, stdout="", stderr="Steam login failed: InvalidPassword"),
        subprocess.CompletedProcess([], 0, stdout="not JSON", stderr=""),
        FileNotFoundError("node"),
        subprocess.TimeoutExpired("node", 66),
    ],
    ids=["login failed", "not JSON", "no node", "no answer in time"],
)
def test_opendota_is_asked_when_the_second_steam_account_fails(session, tmp_path, monkeypatch, outcome):
    add_match(session, GOOD)

    def node(command, **options):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(subprocess, "run", node)
    calls = []
    client = network(calls, opendota=(200, OPENDOTA), valve=(200, zstd.compress(REPLAY)))

    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path, alt=True) == (0, 1)
    assert to("valve.net", calls) == [f"http://replay{CLUSTER}.valve.net/570/{GOOD}_519105714.dem.bz2"]
    assert not (tmp_path / "salts.json").exists()


@pytest.mark.parametrize(
    "body",
    [zstd.compress(os.urandom(4096))[:2000], bz2.compress(os.urandom(4096))[:2000], b"<html>not an archive</html>"],
    ids=["zstd cut short", "bz2 cut short", "not an archive"],
)
def test_a_broken_download_is_retried_not_parsed(session, tmp_path, body):
    add_match(session, GOOD)
    calls = []
    client = network(calls, opendota=(200, OPENDOTA), valve=(200, body))

    assert poll_once(session, client, "", tmp_path / "nowhere", tmp_path) == (0, 0)
    assert to("localhost", calls) == []
    assert session.get(Match, GOOD).replay_state == "pending"
    assert list((tmp_path / "tmp").iterdir()) == []


def player_game(session: Session, account_id: int, match_id: int, age_days: float, wanted: bool) -> None:
    if session.get(PlayerGameList, account_id) is None:
        session.add(PlayerGameList(account_id=account_id, fetched_at=0, replays_wanted=wanted))
    session.add(
        PlayerGame(
            account_id=account_id, match_id=match_id, start_time=int(time.time() - age_days * DAY), hero_id=1,
            player_slot=0, radiant_win=True,
        )
    )  # fmt: skip
    session.commit()


USUAL = json.loads(OPENDOTA)["match_id"]


def test_the_usual_games_of_a_checked_teams_players_become_matches(session, tmp_path, monkeypatch):
    monkeypatch.setattr(poll, "NO_MATCH", set())
    player_game(session, 1001, USUAL, age_days=1, wanted=True)
    player_game(session, 1001, 44, age_days=40, wanted=True)  # too old for its replay
    player_game(session, 1002, 55, age_days=1, wanted=False)  # their team was never checked
    calls = []
    poll_once(session, network(calls, opendota=(200, OPENDOTA)), "", tmp_path / "nowhere", tmp_path)

    assert to("opendota", calls) == [f"https://api.opendota.com/api/matches/{USUAL}"]  # its salt is kept from this answer
    match = session.get(Match, USUAL)
    assert (match.cluster, match.lobby_type, len(match.raw_json["players"])) == (CLUSTER, 7, 10)
    assert "replay_salt" not in match.raw_json  # cut down to what Steam's match details hold
    assert session.query(MatchPlayer).filter_by(match_id=USUAL).count() == 10
    assert session.get(Match, 44) is None and session.get(Match, 55) is None


def test_a_usual_game_opendota_does_not_know_is_asked_for_once(session, tmp_path, monkeypatch):
    monkeypatch.setattr(poll, "NO_MATCH", set())
    player_game(session, 1001, 66, age_days=1, wanted=True)
    calls = []
    client = network(calls)  # OpenDota answers 404
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
    poll_once(session, client, "", tmp_path / "nowhere", tmp_path)
    assert to("opendota", calls) == ["https://api.opendota.com/api/matches/66"]
    assert session.get(Match, 66) is None


def test_storage_counts_each_part_of_the_data_folder(tmp_path):
    for name, size in [("raw/1.jsonl.gz", 100), ("dotanalyst.db", 10), ("dotanalyst.db-wal", 5),
                       ("opendota/matches/1.json", 3), ("tmp/1.dem", 7), ("notes.txt", 2)]:  # fmt: skip
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(bytes(size))
    assert poll.storage(tmp_path) == [
        {"name": "Parser output", "bytes": 100}, {"name": "Database", "bytes": 15},
        {"name": "OpenDota answers", "bytes": 3}, {"name": "Steam answers", "bytes": 0},
        {"name": "Replays being fetched", "bytes": 7}, {"name": "Other", "bytes": 2},
    ]  # fmt: skip
    assert {p["bytes"] for p in poll.storage(tmp_path / "nowhere")} == {0}


def test_the_queue_names_whose_match_it_is(session):
    add_match(session, 1)
    session.add_all([
        Account(account_id=1001, label="Player 1", avatar=""),
        MatchPlayer(match_id=1, player_slot=0, account_id=1001, hero_id=1, items=[]),
        MatchPlayer(match_id=1, player_slot=1, account_id=1002, hero_id=2, items=[]),  # not tracked
        PlayerName(account_id=2001, name="Player 2", avatar="https://example.com/2.jpg"),
    ])  # fmt: skip
    player_game(session, 2001, 1, 0, wanted=True)
    player_game(session, 2002, 1, 0, wanted=False)  # their team is not checked
    player_game(session, 2003, 1, 0, wanted=True)  # no name stored
    league_game(session, 3, 0)
    league_id = session.get(LeagueMatch, 3).league_id

    found = poll.whose(session, [1, 3])
    assert found[1] == {
        "accounts": [{"account_id": 1001, "name": "Player 1", "avatar": None}],
        "usual": [{"account_id": 2001, "name": "Player 2", "avatar": "https://example.com/2.jpg"},
                  {"account_id": 2003, "name": None, "avatar": None}],
        "league": None,
    }  # fmt: skip
    assert found[3]["league"] == f"League {league_id}"  # a tournament not tracked
    session.add(League(league_id=league_id, name="Season 1"))
    assert poll.whose(session, [3])[3]["league"] == "Season 1"


def test_the_steps_say_what_is_planned_and_why_some_of_it_waits(session, tmp_path, monkeypatch):
    def parser_down(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(poll.httpx, "get", parser_down)
    monkeypatch.delenv("STEAM_API_KEY", raising=False)
    monkeypatch.delenv("STEAM_ALT_USER", raising=False)
    poll.STEPS.clear()
    now = time.time()
    for match_id in range(1, 13):
        add_match(session, match_id)
    add_match(session, 20)
    session.get(Match, 20).replay_state, session.get(Match, 20).replay_tried_at = "pending", now - 3
    add_match(session, 30, age_days=40)
    session.commit()

    steps = {s["key"]: s for s in poll.queue(session, tmp_path / "nowhere", tmp_path, now)["steps"]}
    assert list(steps) == ["accounts", "leagues", "usual", "folder", "salts", "downloads", "players", "stats"]
    assert steps["accounts"]["why"] == ["STEAM_API_KEY is not set in .env, so Steam is not asked"]
    assert steps["salts"]["planned"].startswith("none") and "STEAM_ALT_USER" in steps["salts"]["why"][0]
    assert steps["downloads"]["planned"] == "12 due replays downloaded and parsed, 4 at a time"
    retry, parser, old = steps["downloads"]["why"]
    assert retry == "1 tried within the last 10 s wait for their retry, the next in 7 s"
    assert "port 5600" in parser
    assert old.startswith("1 without a replay older than 30 days")
    assert steps["downloads"]["last"] is None  # no poll since the server started

    poll_once(session, network([]), "", tmp_path / "nowhere", tmp_path)  # OpenDota knows none of them
    assert poll.STEPS["downloads"]["what"].startswith("0 of 12 downloaded and parsed")  # every due one, no cap a poll
    assert poll.queue(session, tmp_path / "nowhere", tmp_path)["steps"][5]["last"] == poll.STEPS["downloads"]


def test_progress_counts_parsed_and_waiting_replays_per_profile_and_tournament(session):
    for match_id, age, state in [(1, 0, "parsed"), (2, 0, "none"), (3, 40, "none"), (4, 0, "unavailable"), (5, 40, "pending")]:
        add_match(session, match_id, age)
        session.get(Match, match_id).replay_state = state
    league_game(session, 1, 0)
    league_game(session, 2, 0)
    league_id = session.get(LeagueMatch, 1).league_id
    session.add_all([
        League(league_id=league_id, name="Season 1"),
        Account(account_id=1001, label="Player 1", avatar=""),
        Account(account_id=1002, label="Player 2", avatar="", active=False),  # no longer tracked
        *[MatchPlayer(match_id=m, player_slot=0, account_id=1001, hero_id=1, items=[]) for m in (1, 2, 3, 4)],
        MatchPlayer(match_id=5, player_slot=0, account_id=1002, hero_id=1, items=[]),
    ])  # fmt: skip
    session.commit()

    found = poll.progress(session)
    assert found["overall"] == {"parsed": 1, "waiting": 2}  # 2 is recent, 5 was asked for; 3 is too old, 4 is gone
    assert found["profiles"] == [{"account_id": 1001, "name": "Player 1", "parsed": 1, "waiting": 1}]
    assert found["tournaments"] == [{"league_id": league_id, "name": "Season 1", "parsed": 1, "waiting": 1}]
    assert found["working"] == [] and found["jobs"] == {}


def test_a_match_is_listed_as_worked_on_only_while_its_replay_is(session):
    def work():
        assert poll.WORKING == {1001}
        raise ReplayError("broken")

    with pytest.raises(ReplayError):
        poll.working(1001, work)
    assert poll.WORKING == set()
