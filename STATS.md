# Available stats

What data DotAnalyst has for a match before and after its replay is parsed, and which of it the site uses.

Without a replay there is only the end-of-game scoreboard from the Steam Web API. Parsing the replay adds the timeline: values per minute, events with their times, and map positions.

The lists were checked in November 2026 against the stored Steam JSON of one match and the parser output of one replay. Events that did not happen in that replay, such as buybacks, may exist but are not listed.

## Before parsing

Source: Steam `GetMatchHistoryBySequenceNum`, available for every match and stored in `matches.raw_json`.

### Per match

| Stat | On the site |
|---|---|
| Winner, duration, start time | yes |
| Game mode, lobby type (ranked or not) | yes |
| Region (server cluster) | only to download the replay |
| Kill score of each team, first blood time | no |
| Pre-game duration | no |
| Towers and barracks still standing at the end | no |
| Picks and bans (draft modes only) | no |
| League ID, number of human players | no |

### Per player

| Stat | On the site |
|---|---|
| Hero, team, account (or anonymous) | yes |
| Kills, deaths, assists, last hits, denies | yes |
| GPM, XPM, final net worth, level | yes |
| Hero damage, tower damage, healing | yes |
| Final 6 items and neutral item | yes |
| Leaver status | yes |
| Backpack items, second neutral slot | no |
| Aghanim's Scepter, Aghanim's Shard, Moon Shard consumed | no |
| Gold left at the end, gold spent | no |
| "Scaled" damage and healing values | no |
| Skill build (each ability level-up with its time) | no |
| Facet (`hero_variant`) | no |

### Calculated from it

Win rates, hero stats, K/D/A averages, kill participation, games with other tracked players, and heroes played with and against.

## After parsing

Source: the odota/parser output, stored in `data/raw/{match_id}.jsonl.gz`.

### Derived and shown

| Stat | Table | Where on the site |
|---|---|---|
| Gold, XP, net worth, last hits and denies every minute | `player_minute` | Lead charts, laning table at 10:00 |
| Camps stacked and lotuses used, per minute | `player_minute` | Laning table |
| Every purchase with its time, and when it was built into a bigger item | `purchases` | Item timeline |
| Deaths with time, map position, killer, and whether it was in a teamfight | `deaths` | Death map |
| Position of every hero each second, and whether it is alive | none: read from the raw log when asked | Death playback |
| Teamfights: start, end and deaths; per player whether they took part, damage dealt, healing, and net worth and XP gained | `teamfights`, `teamfight_players` | Teamfight table, unfolded fight |
| Wards: position, placed, removed, lifetime, who destroyed them | `wards` | Ward map |
| Lane per player (top, mid, bot or jungle) | `lanes` | Lane cards, profile roles |

Metrics in `metrics`, shown on the Trends page:

- Lane last hits vs the enemy lane at 10:00
- Lane net worth vs the enemy lane at 10:00
- Observers placed
- Sentries placed
- Wards destroyed
- Observer lifetime
- Fight participation
- Deaths outside fights

### In the output but not used yet

- **Position every second** (so far only used for the death playback): heat maps, movement, time spent in each part of the map
- **Damage log:** damage by target and by ability or item, damage taken, damage to illusions
- **Healing log:** who healed whom, and with what
- **Disables:** stuns and slows, with their durations
- **Gold by source:** creeps, heroes, runes, buildings and more
- **XP by source**
- **Ability and item uses:** casts per ability, and uses of Blink, Black King Bar, Smoke and so on
- **Runes:** how many each player picked up, and which runes
- **Building kills with times:** tower and barracks timings
- **Roshan:** kills, Aegis pick-up, Roshan kills per player
- **Kill events:** kill streaks, multi-kills, first blood
- **Items outside the shop:** starting items, neutral items found
- **Player input:** actions (enough for APM), pings, chat wheel, chat messages
- **Match events:** pauses, disconnects, reconnects, glyph and scan use, courier deaths
- **Extras:** randomed hero, hero prediction, cosmetics

## Adding a stat

Every stat in "not used yet" can be added without downloading anything again. Write the function in `dotanalyst/derive.py` (a new derived table) or `dotanalyst/metrics.py` (one number per player per match), then run `dotanalyst recompute`.

Replays seem to be deleted about 100 days after upload, so matches older than that only ever have the stats from "Before parsing".
