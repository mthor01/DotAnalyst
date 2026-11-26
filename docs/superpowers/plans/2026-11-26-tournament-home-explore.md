# Tournaments home and a richer Explore: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tournaments opens on Search, which shows your tournaments. Explore becomes a front page: live series,
upcoming matches, recent results, starting soon, a calendar, biggest tournaments, and recently finished tournaments
with winners, all filtered by tier, region and online/LAN.

**Architecture:** the poller keeps everything Explore shows:
- Steam's live games: `data/explore/live.json`, each live round
- OpenDota's `/proMatches`: `data/explore/results.json`, each catalog round, at most every 10 minutes
- Liquipedia structures of the Explore tournaments: the existing `data/leagues/<id>.lp.json`
- team logos: `data/team_logos.json`

A new module `dotanalyst/explore.py` writes those files and builds `GET /api/explore` from them without any outside
request. The frontend gets an Explore component and cards, and filters in the browser.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy/SQLite, httpx, pytest; Svelte 5 + TypeScript.

**Spec:** docs/superpowers/specs/2026-11-26-tournament-home-explore-design.md

## Global Constraints

- No new dependencies. The calendar is HTML and CSS.
- Tests never call live APIs: they use fixtures with made-up ids (1001…, 3001…, 9001…) and names ("Team A", "League A").
- Liquipedia: 2 s pace, User-Agent, gzip, caching. Never refetch a stored match or replay.
- One commit per task, straight to main; ask before pushing. Stage files explicitly.
- The user's uncommitted changes in `dotanalyst/poll.py`, `tests/test_poll.py`, `.gitignore`, `README.md`,
  `frontend/src/lib/Progress.svelte`, `frontend/src/lib/api.ts`, `PARSER_CHANGES.md` and `grep.exe.stackdump` are never
  committed.
  - For `poll.py`, the staged blob is HEAD plus our edit only: apply the same edit script to `git show HEAD:<file>`,
    `git hash-object -w`, `git update-index --cacheinfo`.
  - Don't touch `tests/test_poll.py`: tests go to `tests/test_explore.py`.
- Heroes by picture (no heroes on Explore). Team logos: Steam only, never Liquipedia images.
- IMPLEMENTATION.md gets an "Explore" section; the "Tournament browser" section changes for the new home.

## Review Focus

1. A Liquipedia page with no infobox region and no country: region `""` (asked, none). The row must not be re-asked
   every round. Test in Task 1 (`test_region_none_is_kept_as_empty`) and Task 4 (`test_missing_region_skips_empty`).
2. `proMatches` series with `series_id` 0, or a team id 0: grouping must not merge unrelated games. Test in Task 3
   (`test_series_without_id_group_by_league_and_teams`).
3. `live.json` or `results.json` missing or corrupt: Explore answers with empty sections, never 500. Test in Task 4
   (`test_answer_without_files`).
4. A kept structure from before the prize pool change (no `winner` key): the answer treats it as "winner not known".
   Test in Task 4 (`test_finished_winner_unknown_for_old_structure`).
5. The upcoming 24 h window: a match exactly at now+24h is in, past matches are out. Test in Task 4.

---

### Task 1: Region of a tournament

**Files:**
- Modify: `dotanalyst/db.py` (`LeagueCatalog.region: Mapped[str | None]`; `ALTER TABLE league_catalog ADD COLUMN region VARCHAR` in `open_engine`, as the other columns)
- Modify: `dotanalyst/catalog.py` (`REGIONS`, `COUNTRIES`, `region_of`)
- Modify: `dotanalyst/liquipedia.py` (`FIELDS` gains `"region"`; `infobox` returns it)
- Test: `tests/test_catalog.py`, `tests/test_liquipedia.py`

**Interfaces:**
- Produces: `catalog.region_of(region: str, country: str) -> str` returns one of `"Europe"`, `"CIS"`, `"China"`,
  `"SEA"`, `"North America"`, `"South America"`, `"MENA"`, `"International"`, or `""` (none).
  `infobox(...)["region"]` is that value. A row never asked holds `None`.

- [ ] **Step 1: tests**

```python
def test_region_from_infobox_region_then_country():
    assert catalog.region_of("Europe", "") == "Europe"
    assert catalog.region_of("Southeast Asia", "") == "SEA"
    assert catalog.region_of("", "Peru") == "South America"
    assert catalog.region_of("", "Russia") == "CIS"
    assert catalog.region_of("World", "") == "International"

def test_region_none_is_kept_as_empty():
    assert catalog.region_of("", "") == "" and catalog.region_of("Atlantis", "Narnia") == ""

def test_infobox_reads_region():  # test_liquipedia.py
    assert liquipedia.infobox("{{Infobox league\n|country=Germany\n|type=Offline\n}}")["region"] == "Europe"
```

- [ ] **Step 2:** run `uv run pytest tests/test_catalog.py tests/test_liquipedia.py -q`. Expected: the new tests fail.
- [ ] **Step 3:** implement. `REGIONS` maps lower-cased Liquipedia region spellings to the eight names:
  - europe, western europe → Europe
  - cis, eastern europe → CIS
  - china → China
  - southeast asia, sea → SEA
  - north america → North America
  - south america → South America
  - mena, middle east → MENA
  - world, international, global → International

  `COUNTRIES` maps about 60 country names to a region (EU and CIS countries, China, SEA countries, the Americas, MENA
  countries).
- [ ] **Step 4:** run the whole suite. Expected: all pass.
- [ ] **Step 5:** commit `Explore: region of a tournament from Liquipedia`.

### Task 2: The winner from Liquipedia's prize pool, and reading a kept structure

**Files:**
- Modify: `dotanalyst/lp_structure.py` (`winner(pages: dict[str, str]) -> str | None`; `structure()` adds `"winner"`)
- Modify: `dotanalyst/liquipedia.py`:
  - `NOT_STAGES = ("Statistics",)`
  - `VERSION = 4`
  - `kept(league_id: int, data: Path) -> dict | None`
  - `structure_due(row, data, now, finished) -> bool`
- Test: `tests/test_lp_structure.py`, `tests/test_liquipedia.py`

**Interfaces:**
- Produces:
  - `structure(...)["winner"]`: the place-1 opponent's name, or None.
  - `liquipedia.kept(league_id, data)` returns the kept `found` dict whatever its age. It is None when the file is
    missing, unreadable or of another version.
  - `liquipedia.structure_due(...)` is True when `structure()` would ask Liquipedia.

- [ ] **Step 1: tests**

```python
def test_winner_from_prize_pool_slots():
    new = "{{Prize pool|\n|{{Slot|place=1|usdprize=100|{{TeamOpponent|Team A}}}}\n|{{Slot|place=2|{{TeamOpponent|Team B}}}}\n}}"
    old = "{{prize pool slot|place=1|usdprize=100|{{TeamOpponent|Team C}}}}"
    assert lp.winner({"E": new}) == "Team A" and lp.winner({"E": old}) == "Team C"
    assert lp.winner({"E": "no table"}) is None
    assert lp.winner({"E": "{{Slot|place=1|{{TeamOpponent|TBD}}}}"}) is None

def test_kept_and_due(tmp_path):  # test_liquipedia.py: a kept file of VERSION is read whatever its age; another version is not
```

- [ ] **Step 2:** run. Expected: fail.
- [ ] **Step 3:** implement. `winner` takes the first `Slot` or `prize pool slot` block whose `place` is `1` or starts
  with `1-`, then its first `TeamOpponent`, through `opponent()`.
- [ ] **Step 4:** run the suite. Expected: pass. Fix any test that pinned `VERSION` or `NOT_STAGES`.
- [ ] **Step 5:** commit `Explore: tournament winner from Liquipedia's prize pool`.

### Task 3: Kept live games, results and logos (`dotanalyst/explore.py`)

**Files:**
- Create: `dotanalyst/explore.py`
- Modify: `dotanalyst/league_page.py` (`live` uses `explore.parse_live`; `page` calls `explore.remember_logos` with its teams that have a logo)
- Test: `tests/test_explore.py`, fixtures `tests/fixtures/steam_live.json` and `tests/fixtures/pro_matches.json` (made-up ids and names)

**Interfaces:**
- Produces:
  - `parse_live(games: list[dict]) -> list[dict]`: as `league_page.live` today, plus `league_id` and each side's
    `logo_ugc`.
  - `keep_live(games: list[dict], data: Path, now: float) -> None`: writes `{"read": now, "games": parse_live(games)}`.
  - `remember_logos(data: Path, teams: list[dict]) -> None`: dicts with `team_id`, `name`, `logo`; ignores id 0 and
    no logo.
  - `logos(data: Path) -> dict[str, dict]`
  - `RESULTS_SECONDS = 600`
  - `fetch_results(client: httpx.Client, data: Path, now: float) -> int`: asks `https://api.opendota.com/api/proMatches`
    (paced) unless the kept file was read under `RESULTS_SECONDS` ago. Returns the games fetched, 0 when skipped or
    failed. A failure keeps the old file.
  - `series_of(games: list[dict], now: float) -> list[dict]`: finished series, newest end first. Each is LpMatch-shaped:
    - `opponents: [{name, team_id}] * 2`
    - `time` (end), `match_ids`
    - `maps: [{team1side, winner, match_id}]`
    - `score`, `winner`, `best_of`
    - `league_id`, `league_name`

    The series key is `series_id`, else `(leagueid, sorted team ids or names)`. Finished means a team won more than
    `best_of/2`, or the last game ended over 3 hours ago (`DONE_AFTER = 3 * 3600`).

- [ ] **Step 1: tests:**
  - `test_parse_live_reads_series_clock_and_logo`
  - `test_keep_live_writes_file`
  - `test_series_grouped_and_finished_by_wins`
  - `test_series_finished_after_three_hours`
  - `test_series_without_id_group_by_league_and_teams`
  - `test_fetch_results_skips_within_ten_minutes` (MockTransport, counts requests)
  - `test_remember_logos_merges`
  - the existing `league_page` live test still passes
- [ ] **Step 2:** run. Expected: fail (no module).
- [ ] **Step 3:** implement. The OpenDota pace comes from `opendota.pace`.
- [ ] **Step 4:** run the suite. Expected: pass.
- [ ] **Step 5:** commit `Explore: keep live games, recent results and team logos`.

### Task 4: Which tournaments, and the Explore answer

**Files:**
- Modify: `dotanalyst/explore.py`
- Modify: `dotanalyst/api.py` (`/api/explore` returns `explore.answer(session, DATA)`)
- Test: `tests/test_explore.py`

**Interfaces:**
- Produces:
  - `tournaments(session, now) -> list[LeagueCatalog]`: rows with `lp_page`, `lp_tier` 1 to 3, and live or active, or
    `start_date` in the next 14 days (`SOON_DAYS = 14`), or finished within 30 days (`FINISHED_DAYS = 30`). Live first,
    then tier, then prize.
  - `newcomers(session, n=50) -> list[int]`: OpenDota tier premium or professional, no games, never asked; newest id
    first.
  - `missing_region(session) -> list[int]`: `lp_page` set and `region is None`; newest first.
  - `answer(session, data, now=None) -> dict` with:
    - `leagues: {id: catalog.row + region + online}`
    - `live`: the kept games, read within 15 min, sorted by tier, prize, then duration descending, with logos by id
    - `upcoming`: from `kept()` structures of `tournaments()`; time in [now, now+24h], both teams named, at most 20
    - `results`: `series_of`, at most 20
    - `soon`: league ids
    - `calendar`: `[{league_id, start, end, open}]`, tier 1 to 3, overlapping [now-14d, now+42d]
    - `big`: league ids from `catalog.explore`
    - `finished`: `[{league_id, winner: {name, logo} | None}]`
  - Only league rows referenced by a section are in `leagues`.

- [ ] **Step 1: tests:**
  - `test_tournaments_pick_and_order`
  - `test_newcomers_and_missing_region`
  - `test_missing_region_skips_empty`
  - `test_answer_sections` (a catalog, kept structures in `tmp_path`, both files)
  - `test_upcoming_window_24h`
  - `test_answer_without_files`
  - `test_finished_winner_unknown_for_old_structure`
  - `test_calendar_uses_game_dates_and_open_end`
- [ ] **Step 2:** run. Expected: fail.
- [ ] **Step 3:** implement. Upcoming logos are matched by name in any case through `logos()`.
- [ ] **Step 4:** run the suite. Expected: pass.
- [ ] **Step 5:** commit `Explore: the tournaments and the answer of /api/explore`.

### Task 5: The poller fills it

**Files:**
- Modify (staged as HEAD + edit): `dotanalyst/poll.py`
  - `live_step` also calls `explore.keep_live` and asks up to 10 new logos (`steam.team_logo`, then `remember_logos`).
  - `catalog_step`:
    1. `explore.fetch_results`
    2. lookups: the due ones of live, big and subscribed, then `newcomers` (due), then `missing_region` (forced),
       together at most `LOOKUPS`
    3. `liquipedia.structure` for each of `explore.tournaments` while fewer than `STRUCTURES = 15` were due this round
  - The queue description of `catalog` reads "OpenDota's list daily, recent results, Liquipedia for Explore".
- Test: `tests/test_explore.py` (`test_catalog_step_fills_explore`, `test_live_step_keeps_games`, MockTransport)

- [ ] **Step 1:** write the tests. **Step 2:** run them and see them fail.
- [ ] **Step 3:** implement. **Step 4:** run the suite and see it pass.
- [ ] **Step 5:** commit only our hunks with the hash-object staging (Global Constraints):
  `Explore: the poller keeps live games, results and structures`.

### Task 6: Search is the home of Tournaments

**Files:** `frontend/src/Tournaments.svelte`, `frontend/src/lib/settings.svelte.ts`

- Tabs Search, Explore, Teams. The hashes are `tournaments`, `tournaments/explore` and `tournaments/teams`;
  `subscribed` and `search` map to Search.
- With empty text, tier and status, Search shows "Your tournaments", the table of today's Subscribed tab, with
  unsubscribe. With none subscribed, it shows a line pointing to Explore and search.
- The add-by-id form is always shown under it.
- Design ids:
  - `tournaments.search`
  - `tournaments.explore`, with `live`, `upcoming`, `results`, `soon`, `calendar`, `big`, `finished`
  - `tournaments.teams`
- [ ] Build (`npm.cmd run build`) with no new svelte-check errors in these files. Commit
  `Tournaments: Search is home, with your tournaments`.

### Task 7: Explore page

**Files:**
- Create:
  - `frontend/src/Explore.svelte`
  - `frontend/src/lib/TournamentCard.svelte`
  - `frontend/src/lib/Calendar.svelte`
- Modify:
  - `frontend/src/lib/leagues.ts` (types `ExploreAnswer`, `LiveSeries`, `ResultSeries`, `Upcoming`)
  - `frontend/src/Tournaments.svelte`

- **Filter chips:** tier (1, 2, 3, Lower or none), the regions present, and Online/LAN/both. They are kept in
  `localStorage` under `explore_filters`, wrapped in try/catch, like `account_id` in App.svelte.
- **Sections**, in the order of the spec, each with its `data-block`. Empty ones say why, e.g. "Filled within the next
  poll rounds".
- **Results** open `SeriesGames` with `link` as in League.svelte: the match page if the league is subscribed, else
  OpenDota.
- **Calendar:** rows packed greedily, bars coloured `--series-1..3` by tier, a line for today, a click opens
  `#league/<id>`.
- **Visual check** on :8001 at 1400 and 375 px.
- [ ] Build, then commit `Explore: live series, upcoming, results, calendar, finished`.

### Task 8: Documentation and the final check

- IMPLEMENTATION.md:
  - a new "Explore" section with every rule and threshold of the spec
  - the "Tournament browser" section updated for the home page
- The full suite passes, the build passes, and the visual check is done.
- [ ] Commit `Explore: IMPLEMENTATION.md`.
