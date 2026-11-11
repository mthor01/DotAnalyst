# DotAnalyst — Spec

A personal Dota 2 stats site that runs on this PC. It tracks a changeable list of Steam accounts, stores every match's basic data, parses replays into a raw event log, and computes its own stats from that log.

Stack and rules are in [CLAUDE.md](CLAUDE.md). This file says what to build and in what order.

## Decisions from the interview

| Topic | Decision |
|---|---|
| Accounts | A list that changes over time (friends, rivals, pros), managed without code changes |
| Why build it | Own metric definitions, friend-group view, improvement tracking |
| Basic views | Match history, hero performance, teammates and matchups |
| Replay views | Laning phase, economy timelines, fights and deaths, vision and map |
| First custom metrics | Lane CS differential, vision habits, fight participation |
| Replay URLs | OpenDota API supplies `cluster` and `replay_salt`; the site downloads from Valve itself |
| Fetching | The backend polls while it is running |
| Out of scope | Logins and multi-user, hosting beyond this PC, live-game tracking, pro and league matches, global percentiles, MMR tracking, mobile layout, own Game Coordinator client |

Defaults chosen without asking — change any of them before the milestone that uses it:

- Accounts are managed with CLI commands, not a UI form.
- All game modes are stored. The UI filters by mode and lobby type.
- First sync pulls everything the API offers (500 matches per account).
- A downloaded `.dem` is deleted after a successful parse. Files in the Dota client's folder are never modified.
- No migration tool. Raw tables are created once; derived tables are dropped and rebuilt by `recompute`.

## Facts the design depends on

Read from the OpenDota source (`odota/core`, `odota/parser`) in November 2026:

- **`GetMatchDetails` is broken.** Match details come from `GetMatchHistoryBySequenceNum`, using the `match_seq_num` that `GetMatchHistory` returns for each match.
- **`GetMatchHistory`** returns 100 matches per page and 500 at most per account, paged with `start_at_match_id`. The hero filter does not work. `status: 15` means the account has not enabled "Expose Public Match Data". High-rank matches have been omitted from results since March 2025.
- **Party size is not in the Web API.** "Played together" is derived from tracked accounts appearing on the same team.
- **Replay URL** is `http://replay{cluster}.valve.net/570/{match_id}_{replay_salt}.dem.bz2`. The salt is not in the Web API.
- **Parser**: the image `odota/parser:latest` is published on Docker Hub. `POST /` with the raw `.dem` body returns the raw event stream as JSON lines. `GET /healthz` returns `ok`. The server answers HTTP 200 even when the parse fails, so a result is valid only if it contains an `epilogue` line.
- **Event times** are seconds on the game clock, with 0 at the horn.
- **`interval` events** arrive once per second per player and carry `slot`, `x`, `y`, `gold`, `lh`, `denies`, `xp`, `networth`, `level`, `kills`, `deaths`, `assists`, `obs_placed`, `sen_placed`, `camps_stacked`, `rune_pickups`.
- **`player_slot` events** map event slot 0–9 to `player_slot` (0–4 Radiant, 128–132 Dire), which joins replay data to Web API data.

Checked live on 2026-11-11:

- `GetMatchHistoryBySequenceNum` with `matches_requested=1` returns exactly the requested match, with the full scoreboard.
- The parser handles a real replay in about 2 seconds; the output ends with one `epilogue` line that carries the match ID, and gzips to under 1 MB for a 17-minute game.
- `x`/`y` in `interval` events ran from about 61 to 195 in that replay.
- `sqlalchemy`, `httpx` and `pytest` install on Python 3.14.

Not verified — each is the first task of the milestone that needs it:

- Python 3.14 wheels exist for `fastapi` and `uvicorn` (M2).
- OpenDota's `GET /api/matches/{match_id}` returns `cluster` and `replay_salt` for an ordinary public match, and its free rate limit (M3).
- How long Valve keeps replays; assumed 14 days (M3).
- How `x`/`y` map onto a minimap image, and where to get one (M4).

## Prerequisites

1. Install `uv`; it installs Python 3.14 itself. This PC has only Python 3.9.
2. Start Docker Desktop, then `docker run -d -p 127.0.0.1:5600:5600 --restart unless-stopped --name parser odota/parser:latest`. The port is bound to localhost because the parser will fetch any URL it is given.
3. Put `STEAM_API_KEY=...` in `.env`. Commands run as `uv run --env-file .env python -m dotanalyst <command>`, written below as `dotanalyst <command>`.
4. Approve the dependency list: `fastapi`, `uvicorn`, `sqlalchemy`, `httpx`, `pytest`; frontend `svelte`, `vite`, `typescript`, `echarts`. Nothing else is added without asking.

## Data model

Raw data is fetched once and never refetched:

- `accounts` — account_id, label, active flag, whether match history is exposed.
- `matches` — match_id, match_seq_num, start time, duration, winner, mode, lobby type, cluster, the full API response as JSON, and replay state (`none`, `pending`, `parsed`, `unavailable`, `failed`) with last attempt time.
- `match_players` — one row per player per match with the end-of-game numbers from the API.
- `data/raw/{match_id}.jsonl.gz` — the parser output.
- `heroes`, `items` — id-to-name lookups.

Derived tables are rebuilt from raw data by `dotanalyst recompute`: `player_minute`, `purchases`, `deaths`, `teamfights`, `wards`, `lanes`, `metrics`.

## Milestone 1 — Match data and one parsed replay

No Game Coordinator and no OpenDota.

- `add-account <account_id> [label]`, `remove-account <account_id>`, `status`.
- `sync`: for each active account, page through `GetMatchHistory`, then fetch details for match IDs not yet stored. One request per second at most. An account with `status: 15` is flagged and reported, not treated as an error.
- `sync-constants`: hero names from `IEconDOTA2_570/GetHeroes`.
- `parse-replay <file.dem>`: post the file to the parser, reject output with no `epilogue` line, write `data/raw/{match_id}.jsonl.gz`, set replay state to `parsed`. The match ID comes from the file name. A match that is not stored is refused.
- Fixtures: saved API responses, and the saved parser output of the shortest replay in the Dota client folder.

**Done when**

- `uv run pytest` passes with no network access. Tests cover history paging, details parsing, a second `sync` making zero detail requests, the `status: 15` case, and rejection of parser output without `epilogue`.
- `dotanalyst add-account <your id>` followed by `dotanalyst sync` prints the number of matches stored; running `sync` again prints `0 new`.
- `dotanalyst parse-replay "C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\replays\<match_id>.dem"` creates `data/raw/<match_id>.jsonl.gz`, and `dotanalyst status` shows 1 parsed match.

## Milestone 2 — Site for basic stats, with polling

- FastAPI: `GET /api/accounts`, `/api/matches`, `/api/heroes`, `/api/teammates`, `/api/matchups`. All take `account_id`, date range, mode and lobby type filters.
- Polling: a background task in the FastAPI process runs `sync` every `POLL_MINUTES` (default 15). It also parses any new `.dem` in the Dota client folder whose match is stored.
- Svelte pages:
  - **Matches** — filterable table: hero, result, K/D/A, GPM/XPM, duration, items.
  - **Heroes** — sortable table plus a bar chart of win rate and games per hero.
  - **Teammates & matchups** — win rate with each tracked account, and with and against each hero.
- An account switcher applies to every page.
- `npm run build` output is served by FastAPI, so daily use is one process.

**Done when**

- `uv run pytest` passes, including tests of the aggregation queries on fixture data.
- `curl "http://localhost:8000/api/heroes?account_id=<id>"` returns a non-empty JSON array with games and wins per hero.
- `http://localhost:8000/` shows the Matches table, and the Heroes page renders the win-rate bar chart.
- With the server left running, the log shows a poll after `POLL_MINUTES`, and a replay newly downloaded in the Dota client appears as parsed in `dotanalyst status` without a manual command.

## Milestone 3 — Automatic replay download

This comes before the replay stats because replays expire: raw output collected now can be turned into stats later, but a missed replay is gone.

- Each poll, for every stored match with replay state `none` or `pending`: ask OpenDota for `cluster` and `replay_salt`, download the `.dem.bz2` from Valve, decompress it with the standard library, parse, store, delete the `.dem`.
- A match is tried at most once per hour. After 14 days it becomes `unavailable` and is never tried again.
- OpenDota responses are stored, so a salt is never requested twice.

**Done when**

- `uv run pytest` passes with a saved OpenDota response and a fake download. Tests cover the URL built from cluster and salt, the hourly retry limit, the 14-day cutoff, and a failed parse leaving the state `failed` with no raw file written.
- A match played after this milestone shows as `parsed` in `dotanalyst status` within an hour of the poll that found it, with no manual download.

## Milestone 4 — Replay stats and the match page

- `recompute` builds the derived tables from raw output:
  - `player_minute` — gold, XP, net worth, last hits, denies per player per minute.
  - `purchases` — item and time.
  - `deaths` — time, position, killer, whether inside a teamfight.
  - `teamfights` — a window opens 15 s before a hero death and closes after 15 s with no death; it counts as a teamfight when 3 or more heroes died. Per player: took part or not, damage, deaths.
  - `wards` — type, owner, position, placed time, removed time, whether killed.
  - `lanes` — each player's lane from positions between 0:00 and 10:00, and the lane opponent: the enemy in the same lane with the most last hits at 10:00.
- `GET /api/matches/{match_id}` returns the timeline, purchases, deaths, teamfights and wards.
- **Match page** charts:
  - Net worth per player over time (line).
  - Team gold and XP advantage (area).
  - Item purchase timeline.
  - Laning table: last hits, denies, net worth, XP at 5:00 and 10:00 next to the lane opponent's.
  - Ward map and death map (scatter on the minimap).
  - Teamfight list.
- Matches without a parsed replay show the basic scoreboard and say that no replay is available.

**Done when**

- `uv run pytest` passes. Each derivation is tested against the fixture replay with hand-checked expected values: last hits at 10:00 for one player, number of teamfights, number of observer wards, lane and lane opponent for one player.
- Running `dotanalyst recompute` twice yields identical row counts in every derived table.
- `curl http://localhost:8000/api/matches/<parsed match_id>` returns per-minute series for 10 players.
- The match page for a parsed match renders the net worth chart and the ward map.

## Milestone 5 — Custom metrics, trends and group view

One row per player per parsed match in `metrics`. First definitions, to be tuned:

- **Lane CS differential** — own last hits at 10:00 minus the lane opponent's; the same for net worth.
- **Vision habits** — observers placed, sentries placed, enemy wards destroyed, mean observer lifetime in seconds.
- **Fight participation** — share of the match's teamfights the player took part in, kill participation ((kills + assists) / team kills), and deaths outside any teamfight.

Each metric is one Python function from a match's derived rows to a number, so a new metric is one function plus one test.

- `GET /api/metrics?metric=<name>&account_id=<id>` returns the per-match values in time order.
- **Trends page** — pick a metric; line chart of the rolling average over the last 20 parsed matches, per account, with several accounts overlaid.
- **Group page** — tracked accounts side by side: win rate together by pair, and each metric's average per account.

**Done when**

- `uv run pytest` passes, with each metric function tested on the fixture replay.
- `curl "http://localhost:8000/api/metrics?metric=lane_cs_diff&account_id=<id>"` returns one value per parsed match.
- The Trends page renders the rolling line for two accounts at once, and the Group page shows the pair win-rate table.

## Risks

- **High-rank accounts**: their matches may be missing from `GetMatchHistory`. If a tracked account is affected, the fallback is OpenDota's player match list; that is a spec change, not a silent workaround.
- **Private accounts**: a friend who has not enabled "Expose Public Match Data" yields nothing. `status` shows which accounts are affected.
- **OpenDota dependency**: if it stops returning salts, replays still arrive through the Dota client folder.
- **PC off for two weeks**: replays in that window are lost; basic stats are not.
