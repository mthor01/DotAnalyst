# Tournament Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Explore, search and open any Dota league (pro or amateur) and subscribe to it from the Tournaments page.

**Architecture:** A `league_catalog` table holds every league with what OpenDota, Steam's live list and Liquipedia
say about it; the poller keeps it fresh (steps `live` and `catalog`), and search and explore are SQL over it. A
tournament page is built on request: stored games for a subscribed league, else a preview from OpenDota (pro) or
Steam (amateur) kept in `data/leagues/<id>.json`.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy/SQLite, httpx; Svelte 5 + TypeScript. No new dependency.

**Spec:** docs/superpowers/specs/2026-11-26-tournament-browser-design.md

## Global Constraints

- No new dependencies.
- Tests never call live APIs: `httpx.MockTransport` answering from JSON fixtures in `tests/fixtures/`.
- Fixtures use made-up ids (1001, 2001, …), team names ("Team A"), player names ("Player 1"); league names may be invented too.
- Liquipedia: `User-Agent: DotAnalyst/<version> (+https://github.com/mthor01/DotAnalyst)`, `Accept-Encoding: gzip`, at most one request every 2 seconds.
- OpenDota calls go through `opendota.pace()`, Steam calls through `steam.call`/`steam.pace()`.
- Preview games never go into `league_matches`.
- Commit to main after each task; never stage the user's own hunks (poll.py's session_parsed hunk and its `steps()` signature, test_poll.py's session_parsed tests, api.ts's session_parsed hunk, Progress.svelte, README.md, .gitignore). For poll.py and api.ts stage via `git show HEAD:<file>` + the same edit + `git update-index --cacheinfo`.
- Update IMPLEMENTATION.md with every rule and threshold.

## Review Focus

1. A league in Steam's live list that OpenDota's list lacks: it must get a catalog row (name from the live game's `league_name`/"League <id>") and show in Explore — test in Task 2.
2. Liquipedia finding no page: the miss is stored (`lp_checked` set, `lp_page` null) and not asked again for 7 days — test in Task 3.
3. An infobox with a prize pool written "50,000" or missing, dates "2026-11-07" or "2026-11-??": no crash, unknown parts null — test in Task 3.
4. A pro league OpenDota knows no games of (amateur): the page falls back to Steam — test in Task 4.
5. Search text with `%` or `_`: matched literally — test in Task 2.

---

### Task 1: Catalog table and the daily OpenDota refresh

**Files:**
- Modify: `dotanalyst/db.py` (new `LeagueCatalog`)
- Create: `dotanalyst/catalog.py`
- Test: `tests/test_catalog.py`; fixtures `tests/fixtures/od_leagues.json` (4 leagues: one premium, one professional, one excluded, one tier null), `tests/fixtures/od_explorer.json` (`{"rows": [{leagueid, games, first_at, last_at}]}`)

**Interfaces:**
- Produces: `LeagueCatalog(league_id pk, name, tier: str|None, games: int|None, first_game: int|None, last_game: int|None, live_games: int=0, live_seen: int|None, lp_page: str|None, lp_tier: int|None, prize_usd: int|None, start_date: str|None, end_date: str|None, location: str|None, lp_checked: int|None, refreshed: int|None)`.
- Produces: `catalog.refresh(session, client, now: float | None = None) -> int` (rows added); `catalog.STALE = 86400`; `catalog.ACTIVITY_DAYS = 365`.

- [ ] **Step 1: tests**
  - `test_refresh_adds_every_league_and_the_pro_dates`: rows == 4; the explorer row's league has games/first/last; others None.
  - `test_refresh_keeps_rows_and_their_liquipedia_fields`: a row with `lp_tier=1` and a name change in the list → name updated, lp_tier kept, nothing deleted when the list drops a league.
  - `test_refresh_waits_a_day`: second call within STALE makes no request (transport counts calls).
- [ ] **Step 2: run, expect ImportError**
- [ ] **Step 3: implement.** `refresh` reads `max(refreshed)`; skips when younger than STALE. Explorer SQL: `select leagueid, count(*) games, min(start_time) first_at, max(start_time) last_at from matches where start_time > <now - 365 d> group by leagueid` (OpenDota rejects the column names `first`/`last`). A failed explorer answer keeps old dates.
- [ ] **Step 4: run tests, PASS**
- [ ] **Step 5: commit** "Tournament browser: league catalog from OpenDota"

### Task 2: Live leagues, status, search and explore

**Files:** Modify `dotanalyst/catalog.py`; Test `tests/test_catalog.py`; fixture `tests/fixtures/steam_live.json` (3 games in 2 leagues, one league absent from od_leagues.json, `league_name` absent).

**Interfaces:**
- Produces: `catalog.record_live(session, games: list[dict], now: float) -> int` (leagues live); `catalog.LIVE_MINUTES = 15`, `catalog.ACTIVE_DAYS = 30`.
- Produces: `catalog.status(row, now) -> 'live'|'active'|'finished'|'unknown'`.
- Produces: `catalog.search(session, text='', tier='', status='', sort='last', offset=0, limit=50, now=None) -> list[dict]`; tier in `'' | 'premium' | 'professional' | 'amateur'`; sort in `'name' | 'last' | 'games' | 'prize' | 'newest'`.
- Produces: `catalog.explore(session, now=None) -> {"live": [dict], "big": [dict]}`; `catalog.row(r, now, subscribed: set[int]) -> dict` (every column plus `status`, `subscribed`).

- [ ] **Step 1: tests**
  - `test_live_leagues_are_recorded_and_unknown_ones_added` (Review Focus 1): the unlisted league gets a row named "League <id>".
  - `test_a_league_not_seen_again_stops_being_live`: live at t, status 'live' at t+14 min, not at t+16 min; `live_games` of a league not in the next look stays but `live_seen` ages out.
  - `test_status_uses_liquipedias_end_date_without_games`.
  - `test_search_filters_and_sorts`: text case-insensitive; tier amateur covers amateur/excluded/None; sort prize puts None last; `newest` is highest id first.
  - `test_search_text_is_matched_literally` (Review Focus 5): "50%" finds only a name containing "50%".
  - `test_explore_ranks_by_liquipedia_tier_then_prize_then_games` and caps big at 20.
- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: implement.** Status is computed in Python from the row; search filters text/tier in SQL (`ilike` with escaped `%`/`_`), filters status and sorts in Python over the matches (10k rows max). Last game = `last_game` or the epoch of `end_date` when it parses.
- [ ] **Step 4: PASS**
- [ ] **Step 5: commit** "Tournament browser: live leagues, search and explore"

### Task 3: Liquipedia lookup

**Files:** Create `dotanalyst/liquipedia.py`; Test `tests/test_liquipedia.py`; fixtures `tests/fixtures/lp_found.json` (generator=search answer with one page whose wikitext has `{{Infobox league |name=… |liquipediatier=3 |prizepoolusd=50,000 |sdate=2026-11-07 |edate=2026-11-20 |country=Sweden |city=Jönköping |leagueid=1001}}`), `tests/fixtures/lp_none.json` (no `query`).

**Interfaces:**
- Produces: `liquipedia.infobox(wikitext: str) -> dict` with `lp_tier, prize_usd, start_date, end_date, location` (missing → None; tier non-digit → None; date with `??` → None; location = "city, country" or whichever exists).
- Produces: `liquipedia.lookup(session, client, league_id, now=None) -> bool` (found): one request `api.php?action=query&generator=search&gsrsearch=insource:"leagueid=<id>"&gsrlimit=1&prop=revisions&rvprop=content&rvslots=main&format=json`; stores into the catalog row (creating it as "League <id>" if missing), always sets `lp_checked`.
- Produces: `liquipedia.due(row, now) -> bool`: never checked, or checked > 7 days ago and status active/live. `liquipedia.PAUSE = 2.0`, `liquipedia.AGENT`.

- [ ] **Step 1: tests**
  - `test_infobox_reads_the_fields`, `test_infobox_survives_odd_values` (Review Focus 3: "50,000"→50000, "TBA"→None, "2026-11-??"→None, missing fields).
  - `test_lookup_stores_a_found_page_and_sends_the_agent` (asserts request headers User-Agent == AGENT and the `insource` query).
  - `test_a_miss_is_kept_and_not_asked_again_for_a_week` (Review Focus 2).
  - `test_lookups_keep_two_seconds_apart` (pace like opendota's test; conftest zeroes PAUSE for the rest).
- [ ] **Step 2: FAIL** — **Step 3: implement** (wikitext from `pages.*.revisions[0].slots.main["*"]`; `lp_page` is the title; a failed request returns False and sets nothing) — **Step 4: PASS** — **Step 5: commit** "Tournament browser: Liquipedia lookup"

### Task 4: Tournament page data

**Files:** Create `dotanalyst/league_page.py`; Test `tests/test_league_page.py`; fixtures `tests/fixtures/od_league_matches.json` (6 games, 2 series: a Bo3 2–1, a Bo1), `tests/fixtures/od_league_teams.json`; reuse `league_history.json` and `details_by_seq.json` for amateur.

**Interfaces:**
- Consumes: `catalog.row`, `liquipedia.lookup`/`due`, `steam.call`, `steam.details`, `steam.HISTORY`, `opendota.pace`.
- Produces: `league_page.page(session, client, key: str, league_id: int, data: Path = DATA, now=None) -> dict` with `league` (catalog row dict), `source` ('stored'|'opendota'|'steam'|'none'), `teams` [{team_id, name, logo, games, wins, series, series_wins, rating}], `series` [{series_id, type, teams: [a, b], score: [x, y], start_time}], `games` [{match_id, start_time, radiant: {team_id, name}, dire: {…}, radiant_win, radiant_score, dire_score}] newest first.
- Produces: `league_page.series(games) -> list`, `league_page.PREVIEW_HOURS = 6`, `league_page.STEAM_DETAILS = 20`.

- [ ] **Step 1: tests**
  - `test_a_subscribed_league_shows_its_stored_games` (rows from `store_league_match`; no request made).
  - `test_a_pro_league_previews_from_opendota_and_caches_it` (second call, within 6 h, no request; file `data/leagues/<id>.json` written; catalog games/first/last updated).
  - `test_an_amateur_league_falls_back_to_steam` (Review Focus 4: OpenDota answers `[]`; Steam history + details; at most STEAM_DETAILS detail requests).
  - `test_a_finished_league_preview_is_never_fetched_again` (cache 10 days old, last game 60 days ago → no request).
  - `test_series_scores_and_bo_types` (Bo3 2–1, Bo1 1–0; series_type 0/1/2 → 1/3/5 games).
  - `test_preview_games_stay_out_of_league_matches`.
- [ ] **Step 2: FAIL** — **Step 3: implement.** Order: stored when the league is subscribed; else cached file if fresh (or league finished); else OpenDota matches+teams; if OpenDota has no games and there is a key, Steam history (pages until empty or 5) + details of the newest 20 for names and results; games without details keep team ids and no winner. Also runs `liquipedia.lookup` when `due`. — **Step 4: PASS** — **Step 5: commit** "Tournament browser: tournament page data"

### Task 5: Poller steps and API

**Files:** Modify `dotanalyst/poll.py` (steps `live`, `catalog`; `wait_after`; `STORAGE["leagues"] = "Tournament previews"`; queue labels), `dotanalyst/api.py` (routes), `tests/test_poll.py` or `tests/test_catalog.py`.

**Interfaces:**
- Produces: `poll.live_step(session, client, setup) -> int` (Steam `IDOTA2Match_570/GetLiveLeagueGames/v1/`, off without key), `poll.catalog_step(session, client, setup) -> int` (refresh, then Liquipedia lookups for explore's leagues and subscribed ones that are `due`, at most 30 a round). `wait_after('live') == 300`, `wait_after('catalog') == 600`.
- Produces routes: `GET /api/catalog?text&tier&status&sort&offset` → `catalog.search`; `GET /api/explore` → `catalog.explore`; `GET /api/leagues/{id}/page` → `league_page.page`; `POST /api/leagues` takes the name from the catalog when it has the league (OpenDota call only otherwise).

- [ ] **Step 1: tests** — `test_live_step_records_the_live_leagues` (MockTransport with steam_live.json), `test_new_steps_wait_their_own_interval`, `test_catalog_step_looks_up_explores_leagues_once` (second round: no Liquipedia request).
- [ ] **Step 2: FAIL** — **Step 3: implement** — **Step 4: full suite PASS** — **Step 5: commit** (partial staging of poll.py and api.py) "Tournament browser: poller steps and API"

### Task 6: Site

**Files:** Modify `frontend/src/Tournaments.svelte` (tabs Explore, Search, Subscribed, Teams; Explore default), create `frontend/src/League.svelte` (the page), `frontend/src/lib/LeagueRow.svelte` if a row is shared by Explore and Search, modify `frontend/src/App.svelte` (`#league/<id>` like `#team/<id>`, no filters), `frontend/src/lib/api.ts` (types `CatalogRow`, `LeaguePage`; append only, keep the user's hunk out of the commit), `frontend/src/lib/settings.svelte.ts` (DESIGN: `tournaments.explore`, `tournaments.search`, `tournaments.list` relabelled "Subscribed tab", group `league` {header, teams, series, games}).

- [ ] Subscribe/Unsubscribe buttons call `POST /api/leagues` / `remove('leagues/<id>')` and update the row in place; a subscribed league's games link to `#match/<id>`, its teams to `#team/<id>`.
- [ ] Search: text input (debounced 300 ms), tier, status, sort selects; 50 rows and "Show more"; "Add by league id" form kept below.
- [ ] League page credits Liquipedia ("Prize pool, tier, dates and location from Liquipedia, CC BY-SA 3.0") with a link when `lp_page` is set; team logos via `<img>` with team name in alt/title.
- [ ] `npm.cmd run build` clean; visual check of Explore, Search, a pro and an amateur league page, phone width.
- [ ] commit "Tournament browser: Explore, Search and tournament page"

### Task 7: Documentation and final review

- [ ] IMPLEMENTATION.md: new section "Tournament browser" (sources and their costs, catalog refresh, status rules, explore ranking, search, previews and their refresh rule, Liquipedia lookups and credit); update Tournaments tabs, Settings Design list, poll steps and storage.
- [ ] Full test suite, build; self-review of the whole diff against the spec (no subagents in this project).
- [ ] commit "Docs: tournament browser"
