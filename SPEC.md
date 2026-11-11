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
- **Replay URL** is `http://replay{cluster}.valve.net/570/{match_id}_{replay_salt}.dem.bz2`. The salt is not in the Web API. Despite the name, the file is Zstandard-compressed (see below).
- **Parser**: the image `odota/parser:latest` is published on Docker Hub. `POST /` with the raw `.dem` body returns the raw event stream as JSON lines. `GET /healthz` returns `ok`. The server answers HTTP 200 even when the parse fails, so a result is valid only if it contains an `epilogue` line.
- **Event times** are seconds on the game clock, with 0 at the horn.
- **`interval` events** arrive once per second per player and carry `slot`, `x`, `y`, `gold`, `lh`, `denies`, `xp`, `networth`, `level`, `kills`, `deaths`, `assists`, `obs_placed`, `sen_placed`, `camps_stacked`, `rune_pickups`.
- **`player_slot` events** map event slot 0–9 to `player_slot` (0–4 Radiant, 128–132 Dire), which joins replay data to Web API data.

Checked live on 2026-11-11:

- `GetMatchHistoryBySequenceNum` with `matches_requested=1` returns exactly the requested match, with the full scoreboard.
- The parser handles a real replay in about 2 seconds; the output ends with one `epilogue` line that carries the match ID, and gzips to under 1 MB for a 17-minute game.
- `x`/`y` in `interval` events ran from about 61 to 195 in that replay.
- `sqlalchemy`, `httpx`, `pytest`, `fastapi` and `uvicorn` install on Python 3.14.
- OpenDota's `GET /api/matches/{match_id}` returns `replay_salt` and the same `cluster` as the Web API for ordinary public matches, without a key. Its headers show a free limit of 60 calls a minute and about 3,000 a day.
- OpenDota has no salt for some matches (2 of 15 tried, 60 and 120 days old), and asking again did not produce one.
- Valve served every replay tried, up to 75 days old. Each carries a header dated 100 days after upload, which is probably when it is deleted.
- All six replays inspected were Zstandard files under the `.dem.bz2` name, 40–67 MB each. Python 3.14 reads them with the standard library (`compression.zstd`).
- One match takes about 15 seconds to download and parse, and its raw output is about 2.5 MB.

Checked on 2026-11-12 against 69 parsed replays:

- **Map position**: `x`/`y` are map cells. The 7.40 map image from `odota/web` covers cells 64–191, so a point sits at `(x − 64) / 127` from the left and `(191 − y) / 127` from the top. Laying the hero positions of 30 replays over the image puts the lanes on the lane paths. A few positions lie up to 4 cells outside the image and are drawn on its edge.
- **Deaths**: `death_tick` events equal the Web API scoreboard for all 690 players. The combat log reports up to 18 extra deaths per match (Aegis, reincarnation, clones), so it is used only to find the killer.
- **Wards**: `obs_left`/`sen_left` always name an attacker. One from the owner's team means the ward ran out (360 s observer, 420 s sentry); anyone else destroyed it.
- **Purchases**: `DOTA_COMBATLOG_PURCHASE` names the buying hero; only purchases before the horn carry a `slot`.
- **Epilogue match id**: one complete, correct replay carried match id 0. Output is rejected only when it has no `epilogue` line or names a different match.
- **Lanes**: the rule below gives a 2-1-2 split for 136 of 140 teams.

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
- `data/opendota/{match_id}.json.gz` — the OpenDota response that supplied the replay salt.
- `heroes`, `items` — id-to-name lookups.

Derived tables are rebuilt from raw data by `dotanalyst recompute`: `player_minute`, `purchases`, `deaths`, `teamfights`, `teamfight_players`, `wards`, `lanes`, and from Milestone 5 `metrics`.

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

- Run with `uv run --env-file .env uvicorn dotanalyst.api:app`, then open `http://localhost:8000/`.
- FastAPI: `GET /api/accounts`, `/api/constants`, `/api/matches`, `/api/heroes`, `/api/teammates`, `/api/matchups`. The last four take `account_id`, `date_from`, `date_to`, `game_mode` and `lobby_type`.
- `sync-constants` also stores item names, taken from `odota/dotaconstants` because the Web API has no working item list. Hero and item icons load from Valve's CDN.
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

- Each poll, for stored matches with replay state `none` or `pending`: ask OpenDota for `replay_salt`, build the URL from the stored `cluster` and that salt, download from Valve, decompress with the standard library (Zstandard or bz2, told apart by the first bytes), parse, store, delete the `.dem`.
- At most 10 matches per poll, never-tried matches first, newest first. With the default 15-minute poll that is 40 an hour.
- Matches older than 30 days are not downloaded (chosen on 2026-11-11; `MAX_AGE_DAYS` in `poll.py`). They keep state `none`.
- A match is tried at most once per hour. A try that finds no salt or no file leaves it `pending`; once the match is 14 days old such a try makes it `unavailable`, and it is never tried again.
- An OpenDota response with a salt is stored, so a salt is never requested twice.

**Done when**

- `uv run pytest` passes with a saved OpenDota response and a fake download. Tests cover the URL built from cluster and salt, the hourly retry limit, the 14-day cutoff, and a failed parse leaving the state `failed` with no raw file written.
- A match played after this milestone shows as `parsed` in `dotanalyst status` after the poll that found it, with no manual download. If OpenDota has no salt yet, it follows on a later hourly retry.

## Milestone 4 — Replay stats and the match page

- `recompute` drops the derived tables and rebuilds them from raw output (about 1 second per match). The poller computes the same rows for each newly parsed match, so `recompute` is only needed after a derivation changes.
  - `player_minute` — total gold earned, XP, net worth, last hits, denies per player per minute.
  - `purchases` — item and time.
  - `deaths` — time, position, killing hero if any, whether inside a teamfight.
  - `teamfights` — a window opens 15 s before a hero death and closes 15 s after the last one; deaths less than 15 s apart belong to the same window. It counts as a teamfight when 3 or more heroes died.
  - `teamfight_players` — per fight and player: damage dealt to enemy heroes, deaths, and took part or not. A player took part by dealing hero damage, taking hero damage, or dying.
  - `wards` — type, owner, position, placed time, removed time, whether destroyed and by which hero.
  - `lanes` — the zone (top, mid, bot, jungle) where the player spent most of 0:00–10:00, time in a base not counted; and the lane opponent: the enemy in the same lane with the most last hits at 10:00.
- `GET /api/matches/{match_id}` returns the scoreboard and one list per derived table; the lists are empty without a parsed replay. An unknown match is a 404.
- **Match page** (`#match/<id>`, linked from the date in the Matches table):
  - Scoreboard.
  - Net worth per player over time (lines, one panel per team on a shared scale).
  - Team lead in net worth and in XP (area, blue where Radiant leads, red where Dire leads).
  - Laning table: last hits, denies, net worth, XP at 5:00 and 10:00 next to the lane opponent's.
  - Items bought per player in order with the game time; consumables, wards and recipes left out.
  - Ward map and death map on the minimap image (`frontend/public/minimap.webp`, Valve's artwork as redrawn by the OpenDota project).
  - Teamfight list: time, deaths and damage per team, who took part.
- Matches without a parsed replay show the scoreboard and say that no replay is available.

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
- **OpenDota dependency**: if it stops returning salts, replays still arrive through the Dota client folder. It already has no salt for some matches; those end as `unavailable`.
- **Server not running for more than 30 days**: matches that age past the download window are skipped; basic stats are not lost. Raising `MAX_AGE_DAYS` (up to about 100) brings them back while Valve still has the files.
