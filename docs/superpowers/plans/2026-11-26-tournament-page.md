# Tournament Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `#league/<id>` into an event page: bracket tree, groups/standings, live and upcoming series, teams with
logos and rosters, hero/player/head-to-head stats.

**Architecture:** Stats come from stored `LeagueMatch.raw_json` (new `dotanalyst/league_stats.py`). Liquipedia structure
is parsed from wikitext by pure functions (new `dotanalyst/lp_structure.py`), fetched and cached by
`dotanalyst/liquipedia.py`. `league_page.page()` adds the new keys; Svelte draws them in tabs.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, httpx, pytest; Svelte 5 + TypeScript.

**Spec:** docs/superpowers/specs/2026-11-26-tournament-page-design.md

## Global Constraints

- No new dependencies (Python or npm).
- Tests never call live APIs: httpx.MockTransport and fixtures in tests/fixtures/.
- Fixtures: invented team names ("Team A"…), handles ("Player 1"…), ids (match ids 9001…, team ids 3001…, accounts 1001…).
- Liquipedia: `liquipedia.pace()` before every request, header `User-Agent: AGENT`, `Accept-Encoding: gzip`.
- Never refetch stored matches; preview games never go into `league_matches`.
- Heroes by picture: `heroIcon(id)` with the name in `alt` and `title`.
- A new git commit per task, straight to main; stage files explicitly (the user's uncommitted files stay out); message
  ends `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.
- IMPLEMENTATION.md is updated in the task whose rule it describes.

## Review Focus

1. Nested templates inside a Match (`{{Abbr/CET}}` in a date, `{{Map …}}` blocks): the parameter split must respect
   brace depth — Task 3 `test_match_reads_teams_date_ids_and_score`.
2. Future bracket rounds with `TBD` or empty opponents: shown as TBD, never a crash, never upcoming — Task 3
   `test_tbd_matches_parse_and_are_not_upcoming`.
3. Liquipedia down, or no `lp_page`: the page still renders with `liquipedia: null`, an old cache file is kept — Task 4
   `test_a_failed_refresh_keeps_the_old_structure`.
4. Liquipedia names absent from our games: `team_id` 0, no logo, no link — Task 3 `test_identify_by_match_id_then_name`.
5. Anonymous players and games without `picks_bans` in the stats: left out, no crash — Task 1
   `test_anonymous_players_and_games_without_drafts`.

---

### Task 1: Stats from stored games (heroes, players, standings, head-to-head)

**Files:**
- Create: `dotanalyst/league_stats.py`
- Modify: `dotanalyst/league_page.py` (`page()` return), `dotanalyst/api.py` (new route)
- Test: `tests/test_league_stats.py`
- Docs: IMPLEMENTATION.md sections "Tournament standings", "Tournament hero stats", "Tournament player stats",
  "Head-to-head"

**Interfaces:**
- Produces:
  - `heroes(rows: list[LeagueMatch]) -> list[dict]` — `{hero_id, picks, wins, bans, contested}` (contested =
    (picks+bans)/games, 0..1), sorted by contested desc then picks desc. `picks_bans` entries: `is_pick`, `hero_id`,
    `team` (0 Radiant, 1 Dire); a pick wins when its team won. Games without `picks_bans` count in `games` only from
    those with drafts (contested denominator = games that have `picks_bans`).
  - `players(rows: list[LeagueMatch], names: dict[int, tuple[str | None, str | None]]) -> list[dict]` — per account,
    anonymous (`steam.ANONYMOUS`) and `None` left out: `{account_id, name, avatar, team_id, games, wins, kills, deaths,
    assists, kda, gpm, xpm, last_hits, hero_damage, heroes}`; kills…hero_damage are per-game averages rounded to 1
    decimal; `kda` = (kills+assists)/max(deaths,1) on totals, 2 decimals; `team_id` = the team it played most games
    for; `heroes` = its three most played hero ids. Side: `player_slot < 128` is Radiant. Sorted by games desc.
  - `standings(series: list[dict]) -> list[dict]` — from `league_page.series()` output; series with score `[0,0]`
    skipped; `{team_id, name, series_wins, series_losses, map_wins, map_losses}`, sorted by series_wins desc,
    series_losses asc, (map_wins − map_losses) desc, name.
  - `head_to_head(session: Session, a: int, b: int) -> dict` — over all `LeagueMatch` rows where {radiant, dire} team
    ids == {a, b}: `{teams: [side_a, side_b], games: n, wins: [wa, wb], series: [{league_id, league_name, start_time,
    score: [sa, sb]}]}`, series newest first. Stored rows carry no series id, so a series = games of
    one league with less than 6 h between consecutive games. League names from `League`.
  - `page()` adds `standings` (every source) and, when subscribed, `heroes`, `players` (names from `PlayerName`).
  - `GET /api/teams/{a}/vs/{b}` → `head_to_head`; same id twice → 422.

- [ ] **Step 1: Write the failing tests** in `tests/test_league_stats.py` (in-memory session as in
  `test_league_page.py`; build `LeagueMatch` rows with `raw_json` holding `players` and `picks_bans`):
  - `test_heroes_count_picks_wins_bans_and_contested` — 2 games, hero 1 picked by the winner in both, hero 2 banned in
    one: hero 1 `(picks, wins, bans, contested) == (2, 2, 0, 1.0)`, hero 2 `== (0, 0, 1, 0.5)`, hero 1 first.
  - `test_players_average_per_game_and_take_their_main_team` — one account, 2 games for team 3001 and 1 for 3002,
    kills 10/0/5, deaths 2/2/0, assists 0/0/3: `games == 3`, `kills == 5.0`, `kda == round(18/4, 2)`,
    `team_id == 3001`, `name` from the names dict.
  - `test_anonymous_players_and_games_without_drafts` — a game with an anonymous player and no `picks_bans` key: the
    anonymous account is absent from `players`, `heroes` still counts the other game's draft only, contested of a
    hero picked there is 1.0.
  - `test_standings_order_and_skip_unplayed` — three series (A beats B 2–0, B beats C 2–1, A vs C 0–0): order A, B, C;
    B `(series_wins, series_losses, map_wins, map_losses) == (1, 1, 2, 3)`; C has `series_losses == 1`.
  - `test_head_to_head_across_leagues` — games A vs B in league 1001 (two, 1 h apart, A wins both) and league 1002
    (one, B wins): `wins == [2, 1]`, two series, newest first with `league_name` set, score of the 1001 series `[2, 0]`.
  - `test_page_adds_stats_for_a_subscribed_league` — reuse `test_league_page.client`; subscribed league → `page` has
    `heroes`, `players`, `standings`; unsubscribed pro preview → `standings` only, no `heroes` key.
- [ ] **Step 2: Run** `uv run pytest tests/test_league_stats.py -q` — Expected: FAIL (ModuleNotFoundError
  `dotanalyst.league_stats`).
- [ ] **Step 3: Implement** the four functions, wire `page()` and the route. `page()` passes the subscribed rows it
  already loads; names: one `select(PlayerName)` over the accounts seen.
- [ ] **Step 4: Run** `uv run pytest tests/test_league_stats.py tests/test_league_page.py -q` — Expected: all pass.
- [ ] **Step 5: Update IMPLEMENTATION.md** (four sections, rules and limits as above) and **commit**
  `Tournament page: hero, player, standings and head-to-head stats`.

### Task 2: Logos and rosters from stored games

**Files:**
- Modify: `dotanalyst/league_stats.py`, `dotanalyst/league_page.py`
- Test: `tests/test_league_stats.py`
- Docs: IMPLEMENTATION.md "Tournament browser" (logos), new "Tournament rosters"

**Interfaces:**
- Consumes: `steam.team_logo(client, key, ugc_id, data) -> str | None` (cached in `data/logos.json`).
- Produces:
  - `played_rosters(rows: list[LeagueMatch], names: dict[int, tuple[str | None, str | None]]) -> dict[int, list[dict]]`
    — team_id → `[{account_id, name, avatar, games}]` most games first, anonymous left out.
  - `logo_ids(rows: list[LeagueMatch]) -> dict[int, int]` — team_id → UGC id from its newest game with
    `radiant_logo`/`dire_logo` non-zero.
  - `page()` for a subscribed league: each team without a logo gets `team_logo(...)` of its UGC id; `rosters` key
    (team_id as string → list).

- [ ] **Step 1: Failing tests:** `test_played_rosters_by_team` (two accounts for 3001, one with 2 games first; anonymous
  absent) and `test_stored_teams_get_their_steam_logo` (write `{"77": "https://example.invalid/77.png"}` to
  `tmp_path/logos.json`, a stored game with `radiant_logo: 77` for team 3001; `page()` → that team's `logo` is the URL
  and no request went to Steam's logo endpoint).
- [ ] **Step 2: Run** `uv run pytest tests/test_league_stats.py -q` — Expected: the two new tests FAIL.
- [ ] **Step 3: Implement**; `page()` passes its `data` to `team_logo`.
- [ ] **Step 4: Run** `uv run pytest tests/test_league_stats.py tests/test_league_page.py -q` — Expected: pass.
- [ ] **Step 5: Docs, commit** `Tournament page: Steam logos and rosters of stored teams`.

### Task 3: Liquipedia wikitext parser

**Files:**
- Create: `dotanalyst/lp_structure.py`, `tests/test_lp_structure.py`, `tests/fixtures/lp_event.txt`,
  `tests/fixtures/lp_layout.txt`
- Docs: IMPLEMENTATION.md new "Liquipedia brackets and groups"

Fixtures (invented): `lp_layout.txt` — a small double elimination layout in the commons format, this exact text:

```
{{TemplateMatch|matchid=R01-M001|header=!u3!x}}{{TemplateMatch|matchid=R01-M002}}
{{TemplateMatch|matchid=R02-M001|toupper=R01-M001|tolower=R01-M002|header=!u2!x}}
{{TemplateMatch|matchid=R04-M001|root=true|toupper=R02-M001|tolower=R03-M001|bracketreset=RxMBR|header=!zz!x}}
{{TemplateMatch|matchid=RxMBR}}

{{TemplateMatch|matchid=R02-M002|header=!lx!1}}
{{TemplateMatch|matchid=R03-M001|tolower=R02-M002|header=!l2!x}}
```

`lp_event.txt` — an infobox with `leagueid=1002`; `==Group Stage==` / `===Group A===` with a `{{GroupStandings|…|title=Standings|{{TeamOpponent|Team A}}|{{TeamOpponent|Team B}}|{{TeamOpponent|Team C}}}}`
and a `{{Matchlist|id=x|M1={{Match|opponent1={{TeamOpponent|Team A}}|opponent2={{TeamOpponent|Team B}}|date=November 13, 2026 - 11:00 {{Abbr/CET}}|matchid1=9001|matchid2=9002|map1={{Map|team1side=radiant|winner=1}}|map2={{Map|team1side=dire|winner=1}}|map3={{Map|finished=skip}}}}|M2=… Team B vs Team C 2–1 …|M3=… Team A vs Team C, date November 30, 2026 - 18:00 {{Abbr/CEST}}, no maps}}`;
`==Playoffs==` with `{{Bracket|Bracket/4DE|id=y|R1M1header=Semifinals|R1M1={{Match …}}|R1M2=…|R2M1=…|R4M1={{Match|opponent1={{TeamOpponent|}}|opponent2={{TeamOpponent|TBD}}}}}}`;
`{{TeamParticipants|{{Opponent|Team A|players={{Persons|{{Person|role=1|Player 1}}|{{Person|role=5|Player 2|status=sub}}}}}}}}`.

**Interfaces:**
- Produces (all pure, `wikitext: str` in):
  - `blocks(text: str, name: str) -> list[tuple[int, str]]` — every `{{name…}}` at any depth (brace-balanced), as
    (offset, body without the outer braces).
  - `params(body: str) -> dict[str, str]` — top-level `|key=value` (and positional `1`, `2`…) of a template body,
    splitting only at brace depth 0 and `[[ ]]` depth 0.
  - `when(date: str) -> int | None` — `"November 13, 2026 - 11:00 {{Abbr/CET}}"` → epoch seconds;
    `ZONES = {"UTC": 0, "GMT": 0, "CET": 1, "CEST": 2, "EET": 2, "EEST": 3, "MSK": 3, "SGT": 8, "CST": 8, "KST": 9,
    "PST": -8, "PDT": -7, "EST": -5, "EDT": -4, "BRT": -3, "PET": -5}`; unknown zone → UTC; no time → noon UTC; not a
    date → None.
  - `match(body: str) -> dict` — `{opponents: [name|None, name|None], time, match_ids: [int], maps: [{team1side,
    winner}], score: [a, b], winner: 0|1|None}`; names `TBD`/empty → None; `finished=skip` maps dropped; winner = the
    Match's own `winner=` (1/2 → 0/1) when given; else None while any listed map has no winner; else the higher score
    (a tie → None).
  - `ROUNDS = {"!u1!": "Grand Final"…}` per spec, plus `round_name(code: str | None, index: int) -> str`.
  - `layout(wikitext: str) -> list[dict]` — `[{id, toupper, tolower, header, root, reset, section}]`, section
    "upper"/"lower" per the spec's header rule.
  - `bracket(body: str, slots: list[dict]) -> dict` — `{sections: [{name, rounds: [{name, matches: [M]}]}]}`; `M` =
    `match()` + `id` + `feeders: [ids]` + `header`; rounds by the R number in order; `RxMBR` only if it has a played
    map; page `R1M1header=` names beat the code.
  - `structure(pages: dict[str, str], layouts: dict[str, list[dict]], now: float) -> dict` — over the event page and
    its children: `{brackets: [{title, sections}], groups: [{title, rows}], upcoming: [M], rosters: [{name, players:
    [{handle, role, sub}]}], matches: [M]}`; title = nearest `==…==` heading above the template, else the page's last
    path part. Group rows: `{name, series_wins, series_losses, map_wins, map_losses}` from same-page matches between
    members, ordered as `league_stats.standings`. Upcoming per spec (no map played, both named, time ≥ now − 12 h,
    soonest first, ≤ 10).
  - `layout_names(pages: dict[str, str]) -> set[str]` — the `Bracket/<x>` names used.
  - `identify(found: dict, games: list[dict], teams: list[dict]) -> dict` — sets `team_id` (0 when unknown) on every
    opponent dict (opponents become `{name, team_id}`) and roster; match id first (`team1side` of the map with that
    `matchid<k>` against the game's radiant/dire ids), then case-insensitive name against `teams`.

- [ ] **Step 1: Failing tests** in `tests/test_lp_structure.py`:
  - `test_params_respect_nested_braces` — `params("Match|date=X {{Abbr/CET}}|map1={{Map|winner=1}}|a=b")` keys
    `date, map1, a`, `date == "X {{Abbr/CET}}"`.
  - `test_when_reads_the_zone` — `when("November 13, 2026 - 11:00 {{Abbr/CET}}") == calendar.timegm((2026,11,13,10,0,0))`;
    unknown zone `XYZ` → 11:00 UTC; `"TBA"` → None.
  - `test_match_reads_teams_date_ids_and_score` — first Matchlist match of the fixture: opponents
    `["Team A", "Team B"]`, match_ids `[9001, 9002]`, score `[2, 0]`, winner 0, two maps.
  - `test_layout_sections_and_feeders` — fixture layout: R02-M002 and R03-M001 are "lower", others "upper"; R04-M001
    root with feeders R02-M001 and R03-M001.
  - `test_round_names_page_header_beats_code_and_unknown_code` — upper R1 named "Semifinals" (the page's
    `R1M1header`), upper R2 "Upper Bracket Final" (`!u2!`), lower R2 "Lower Bracket Round 1" (`!lx!1`), lower R3 "Lower
    Bracket Final" (`!l2!`), R4 (`!zz!`) → "Round 4".
  - `test_tbd_matches_parse_and_are_not_upcoming` — R4M1 opponents `[None, None]`, not in `upcoming`.
  - `test_group_standings_from_same_page_matches` — Group A rows A (1–0, 2–0), B (1–1, 2–3)… order A, B, C.
  - `test_upcoming_soonest_first_and_not_stale` — with `now` = Nov 20 2026 the Nov 30 match is upcoming; with now = Dec
    2 2026 it is not.
  - `test_rosters` — Team A players `[{"handle": "Player 1", "role": "1", "sub": False}, {"handle": "Player 2", "role":
    "5", "sub": True}]`.
  - `test_identify_by_match_id_then_name` — games: match 9001 radiant 3001 / dire 3002; teams `[{"team_id": 3003,
    "name": "team c"}]`: Team A → 3001 (map1 team1side radiant), Team B → 3002, Team C → 3003 by name, an unknown
    "Team Z" → 0.
- [ ] **Step 2: Run** `uv run pytest tests/test_lp_structure.py -q` — Expected: FAIL (ModuleNotFoundError).
- [ ] **Step 3: Implement** `lp_structure.py`.
- [ ] **Step 4: Run** the same — Expected: all pass.
- [ ] **Step 5: Docs, commit** `Tournament page: Liquipedia bracket and group parser`.

### Task 4: Fetching and caching the Liquipedia structure

**Files:**
- Modify: `dotanalyst/liquipedia.py`, `dotanalyst/league_page.py`
- Test: `tests/test_liquipedia.py`, fixtures `tests/fixtures/lp_allpages.json`, `tests/fixtures/lp_pages.json`
  (a batched revisions answer: the event page from `lp_event.txt`, child `X/Playoffs`, child `X/Region` with its own
  `{{Infobox league|leagueid=1999}}`), `tests/fixtures/lp_layout.json` (commons answer wrapping `lp_layout.txt`).
- Docs: IMPLEMENTATION.md "Liquipedia brackets and groups" (fetching, caching), "Storage" (`brackets.json`,
  `<id>.lp.json`)

**Interfaces:**
- Consumes: `lp_structure.structure`, `layout`, `layout_names`, `identify`.
- Produces:
  - `COMMONS = "https://liquipedia.net/commons/api.php"`, `MAX_PAGES = 50`.
  - `pages(client, title: str, league_id: int) -> dict[str, str] | None` — allpages (`apprefix=title + "/"`, direct
    children only, not `Statistics`/`prizepool`), then one revisions request for the event page + children; children
    with an infobox `leagueid` other than `league_id` dropped; None on any failed request.
  - `layouts(client, names: set[str], data: Path) -> dict[str, list[dict]]` — `data/leagues/brackets.json`, a layout
    fetched (one request for all missing, `titles=Template:Bracket/a|…`) only when missing; never again.
  - `structure(client, row: LeagueCatalog, data: Path, now: float, finished: bool) -> dict | None` — cache
    `data/leagues/<id>.lp.json` `{fetched, page, found}`; fresh when `page == row.lp_page` and (younger than
    `league_page.PREVIEW_HOURS` or finished); a failed fetch returns the old `found` (or None).
  - `page()` adds `liquipedia` = `identify(structure(...), games, teams)` + `page`, or None without `lp_page`.

- [ ] **Step 1: Failing tests:** `test_structure_fetches_pages_and_layouts_once` (3 Liquipedia requests: allpages,
  revisions, commons; second call within 6 h: 0; after 7 h with the league active: 2, the layout not again),
  `test_a_qualifier_child_is_dropped` (no group or bracket from `X/Region`), `test_a_failed_refresh_keeps_the_old_structure`
  (cached file 7 h old, transport answers 500 → returns the old structure), `test_page_has_no_liquipedia_without_a_page`.
- [ ] **Step 2: Run** `uv run pytest tests/test_liquipedia.py -q` — Expected: new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: whole suite passes.
- [ ] **Step 5: Docs, commit** `Tournament page: fetch and cache Liquipedia brackets and groups`.

### Task 5: Live series

**Files:**
- Modify: `dotanalyst/league_page.py`
- Test: `tests/test_league_page.py` (fixture `steam_live.json` exists)
- Docs: IMPLEMENTATION.md "Tournament live series"

**Interfaces:**
- Produces: `live(client, key: str, league_id: int) -> list[dict]` — `steam.call(client, key, poll.LIVE ... )`
  (import the path constant without a cycle: move nothing, use the literal `"IDOTA2Match_570/GetLiveLeagueGames/v1/"`
  as `LIVE` in league_page), filtered to `league_id`: `[{match_id, radiant: Side, dire: Side, series: [rw, dw],
  best_of, duration, score: [r, d]}]` (`scoreboard.duration`, `scoreboard.radiant.score`, `scoreboard.dire.score` when
  present, else None). `page()` adds `live` only when `catalog.status(row, now) == "live"` and a key; a SteamError →
  `[]`.

- [ ] **Step 1: Failing tests:** `test_a_live_league_shows_its_live_games` (row with `live_seen=NOW`, `live_games=1`;
  transport answers the fixture for `GetLiveLeagueGames`; `page["live"][0]["series"] == [0, 1]`, teams Team A / Team
  B) and `test_no_live_call_for_a_league_not_live` (no request to GetLiveLeagueGames).
- [ ] **Step 2: Run** `uv run pytest tests/test_league_page.py -q` — Expected: two FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/test_league_page.py -q` — Expected: pass.
- [ ] **Step 5: Docs, commit** `Tournament page: live series`.

### Task 6: The page in Svelte

**Files:**
- Modify: `frontend/src/lib/leagues.ts` (types for every new key), `frontend/src/League.svelte` (tabs and sections),
  `frontend/src/App.svelte` (route `^league\/(\d+)(?:\/(\w+))?$`, tab prop), `frontend/src/lib/settings.svelte.ts`
  (Design tree: league blocks `live`, `upcoming`, `bracket`, `groups`, `teams`, `heroes`, `players`, `h2h`, `series`,
  `games` and the tabs)
- Create: `frontend/src/lib/Bracket.svelte`
- Docs: IMPLEMENTATION.md "Design" note for the tournament page tabs

Decisions: tabs Overview / Teams / Stats / Games (`#league/<id>`, `/teams`, `/stats`, `/games`), hidden-tab fallback
via `shownTab` like Tournaments.svelte. Bracket: one column per round, matches placed at the mean height of their
feeders (leaves stacked), SVG lines feeder → match, upper then lower section, horizontal scroll in its own box. Match
box: logo (from the page's teams by `team_id`) + name + score per opponent, winner bold, TBD muted; click → the first
match id: `#match/<id>` when subscribed, else OpenDota. Stats tables sortable by header click. Head-to-head: two
`<select>`s of the league's teams, fetch `teams/{a}/vs/{b}`. A section with no data is omitted. Teams rows expand to
roster (Liquipedia's by name/team_id, else `rosters`).

- [ ] **Step 1:** Implement; `npm.cmd run build` in frontend/ — Expected: build succeeds with no new warnings.
- [ ] **Step 2:** Visual check (memory visual-check-recipe: `$SP/serve2.py` on :8001, headless Edge, `look.mjs`) of a
  subscribed league (stats tab), a Liquipedia pro league (overview with bracket and groups), an amateur preview
  (standings fallback) at 1400 px and 420 px.
- [ ] **Step 3: Docs, commit** `Tournament page: tabs, bracket, groups, teams and stats in the site`.
