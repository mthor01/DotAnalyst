# How DotAnalyst works things out

Steam and the replay parser hand over raw facts: a scoreboard, and a log of events and positions. Everything else on the site is worked out from those by rules written in this project. This file records each of those rules as it stands today: what it reads, what it decides, the numbers it uses, and where it is known to be wrong.

It is checked with every change and updated when a rule changes (see [CLAUDE.md](CLAUDE.md)). What the site is and how it is built is in [SPEC.md](SPEC.md); which data exists at all is in [STATS.md](STATS.md).

Terms used below:

- **Slot**: a player's place in the match. Player slots 0–4 are Radiant, 128–132 are Dire.
- **Map cell**: the unit of replay positions. The map runs from about cell 64 to cell 191 in both directions, with the Radiant base bottom left.
- **Interval**: the line the parser writes once a second for every player, with position, gold, experience, level and more.
- **Combat log**: the parser's lines for damage, heals, deaths and purchases, each naming a source and a target.
- **Game clock**: seconds, 0 at the horn. The heroes appear at −89.

## From the replay

All of this is in `dotanalyst/derive.py` and is stored in the derived tables. `dotanalyst recompute` throws those tables away and builds them again, so a changed rule reaches old matches by running it.

### Lane of a player

Read from: the position in every interval from 0:00 to 10:00.

Each second votes for the zone the hero stands in, and the zone with the most votes is the player's lane.

| Zone | Where (x, y in map cells) |
|---|---|
| No vote | In a base: both x and y below 96, or both above 160 |
| Mid | x and y less than 14 apart |
| Top | Above the diagonal (y > x) and at the map's edge: x below 96 or y above 160 |
| Bottom | Below the diagonal and at the map's edge: y below 96 or x above 160 |
| Jungle | Everything else |

A player who never left the base has no lane.

Checked: gives a 2-1-2 split for 136 of 140 teams (69 replays, November 2026).

Known limits: a roaming support gets the zone it spent most seconds in, and "jungle" does not say whose jungle.

### Teamfights

Read from: the `death_tick` events (the deaths that count on the scoreboard).

Deaths less than 15 seconds apart belong to one group. A group of 3 or more deaths is a teamfight. Its window starts 15 seconds before the first death and ends 15 seconds after the last (`FIGHT_GAP`, `FIGHT_DEATHS`).

Per fight and player:

- **Took part**: dealt damage to an enemy hero, took damage from one, or died, inside the window.
- **Damage**: the combat log's damage of the hero on enemy heroes inside the window. Illusions as targets are left out.
- **Healing**: as under "Healing" below, inside the window.
- **Net worth and experience gained**: the value at the end of the window minus the value at its start. Net worth is used, not gold earned, so that gold lost by dying or spent on a buyback counts.

The site lists only fights that start at 10:00 or later (`FIGHTS_FROM` in `Match.svelte`): three deaths before that are a skirmish in a lane. The table and the fight metrics hold all of them.

### Deaths

Read from: `death_tick` for the death itself, the combat log for the killer, the interval of that second for the place.

The combat log reports deaths that do not count (Aegis, reincarnation, clones: up to 18 extra in a match), so it only supplies the killer: the source of a combat-log death of the same hero in the same second, the one before or the one after. A death without such a line, or with a source that is not a hero, has no killer.

A death is "in a teamfight" when its second lies inside a fight's window.

Checked: `death_tick` equals the scoreboard for all 690 players of 69 replays.

### Wards

Read from: `obs` and `sen` (placed), `obs_left` and `sen_left` (gone).

The parser always names an attacker when a ward goes. If the attacker is a hero of the owner's team, the ward ran out. If it is an enemy hero, that hero destroyed it. Any other attacker (a creep, a building) also counts as destroyed, with nobody credited. A ward without a "left" line stood to the end.

### Lotuses collected

Read from: positions only. The parser reports who eats a lotus, not who picks one up, so the pools' rules (since patch 7.38) are played through against the hero positions.

- The two pools are at cells (70.3, 161.3) and (186.0, 93.5): where heroes stood whenever three lotuses merged into a great one, over 240 replays.
- A pool grows one lotus every 180 seconds and holds 6 at most.
- A lotus that grows from 35:00 on is a great lotus and counts as 3. From 60:00 on it is a greater lotus and counts as 6.
- A living hero within 3 cells of a pool for 2 seconds in a row takes one lotus each second, the oldest first. Of several heroes there, the one who has stood there longest takes it.

Checked on 240 replays against the lotuses each hero ate or still held at the end: equal for 7 heroes in 10, within one for 9 in 10.

Known limits: two heroes at a pool (only the one there longer gets lotuses), a lotus handed to an ally (stays with the collector), and Turbo, whose pools grow twice as fast.

### Camps pulled

Read from: the combat log's damage and deaths between lane creeps, neutral creeps and heroes.

A pull shows as lane creeps and neutral creeps killing each other.

- Such kills by the same side's lane creeps less than 25 seconds apart are one pull (`PULL_GAP`).
- The pull counts for the hero of the lane creeps' team who last traded hits with a neutral creep in the 30 seconds before its first kill (`PULL_LEAD`). Without such a hero nobody is credited.
- A neutral creep that a hero has taken over is left out: it fights lane creeps without any pull.

Known limits: a wave that walks into a camp the enemy pulled counts for whoever of its own team hit a neutral creep just before, and late in a game a hero farming a camp beside a pushed wave gets a pull.

Not checked against anything: no other source records pulls.

### Healing

Read from: the combat log's heals whose source and target are both heroes. Illusions as targets are left out.

A heal counts when the healer and the healed hero are on the same team and are **not the same hero**. What a hero heals itself (regeneration from items, lifesteal) is not counted, since November 2026: it says how the hero lasted, not what it did for the team.

`player_minute.healing` is the sum up to each full minute; `teamfight_players.healing` the sum inside a fight's window.

Known limit: a heal from a summoned unit is not credited to its owner.

### Hero damage per minute

Not worked out: `player_minute.hero_damage` is the replay's own running count from the interval of each full minute. The damage inside a teamfight is added up from the combat log instead (see Teamfights), so the two do not have to agree.

### Camps stacked

Not worked out: the replay's own count from the interval.

### Purchases and what they were built into

Read from: the combat log's purchases, and the `recipes` table (item → components, from dotaconstants).

The log reports a finished item as a purchase of its own at the moment its parts come together. For each such item, every component of its recipe uses up the newest earlier purchase of that component by the same player that is not used up yet; that purchase gets `built_at`, the time of the finished item.

Power Treads take a Band of Elvenskin or a Robe in the place of the listed Belt of Strength.

Known limit: a part an ally bought is not found, so the part of the buyer stays an item of its own.

### Skill points

Read from: `DOTA_ABILITY_LEVEL` events.

- At the second a hero appears, the log lists all its abilities. That list is skipped, as is any line with a level below 1.
- Shadow Fiend's three Shadowrazes level together and count as one point.
- An ability named `special_bonus_*` is a talent, except `special_bonus_attributes`, which is a point put into the attributes and shown as a skill point.

The hero's level beside each point is the level in the interval of that second.

### Buildings

Read from: the combat log's deaths of units named `npc_dota_goodguys_…` or `npc_dota_badguys_…` that are a tower, a barracks or the Ancient. The filler buildings in the bases are left out.

The two tier-4 towers of a side share one name. The first of them to fall is drawn as the one listed first in `MiniMap.svelte`; the log does not say which it was.

### Positions

Not stored. `positions()` reads the intervals of a time span from the raw log when a page asks (`GET /api/matches/{id}/positions`): ten rows a second for every match would be too much to keep for views that are rarely opened.

## Metrics

One function each in `dotanalyst/metrics.py`, stored per player and match in `metrics`. A metric that does not apply has no row, so averages cover only the matches where the number means something.

| Metric | Rule |
|---|---|
| `lane_cs_diff`, `lane_nw_diff` | Last hits (or net worth) at 10:00 of all heroes of the player's side in the player's lane, minus the same sum of the enemies in that lane. No value for a jungler, for a lane without enemies, or in a match shorter than 10 minutes. Both players of a lane get the same value |
| `obs_placed`, `sen_placed` | Wards of that kind the player placed |
| `wards_destroyed` | Enemy wards of either kind the player destroyed |
| `obs_lifetime` | Mean seconds the player's observers stood. One still standing at the end is left out |
| `fight_participation` | Share of the match's teamfights the player took part in |
| `kill_participation` | (kills + assists) / kills of the team, from the scoreboard |
| `deaths_outside_fights` | Deaths outside every fight window |

Known limit: the lane differences describe the lane, not the player, and a lane of two against one compares two heroes' sums with one hero's.

## From the scoreboards

In `dotanalyst/queries.py`. Nothing here is stored; it is counted on each request.

### Filters: time and season

Every account page and every team page take a time span and a season; account pages also take lobby and mode.

- **Time** is last month, last 3, 6 or 12 months, all time, or two dates. A span of months starts on today's date that many calendar months back (`monthsAgo` in `App.svelte`) and has no end. The dates are local days and both count: from 1 Nov to 3 Nov is all of the 1st to the end of the 3rd (`between` in `queries.py`).
- **Season** is one of the tracked leagues (`LEAGUES` in `steam.py`). A match belongs to it when `league_matches` has it under that league id, so on an account page a season shows only league games the account itself played.
- A known team without a game in the filters gets an empty page, not "unknown team".

### Played with a tracked account

Steam's data does not say who queued together. A match counts as "with tracked players" when another active tracked account was on the same team.

### Position 1–5 of a player

Every row of an account's match list carries the player's position, 1 (carry) to 5 (hard support), worked out per team on each request (`positions` in `queries.py`).

- **Lane** is the lane from the replay (see Lane of a player), seen from the team's side: the safe lane is bottom for Radiant and top for Dire.
- **Farm** is the scoreboard's last hits at the end of the match; equal last hits go by net worth.
- The safe lane's most farmed player is 1 and its least farmed 5, the mid is 2, the off lane's most farmed 3 and least farmed 4. A player alone in the safe or off lane gets only the first of those (1 or 3).
- Everyone else (a jungler, a third player in a lane, a lane the replay could not tell, every player of a match without a parsed replay) takes the positions still open, the most farmed the lowest.

Checked: the 7 tracked accounts' matches give each account one or two clear main positions; for the parsed ones, supports come out 4 and 5 and cores 1 to 3 (November 2026).

Known limits: without a parsed replay (most matches) the position is only the team's farm order, so a mid who out-farms the carry is 1 and the carry 2, and a support with a big late game can rank above a core. With a replay, a support who lanes alone and a core who jungles take the open places by farm, which can swap 4 and 5 with 1 or 3.

### League teams

Built from the drafts and scoreboards of the league games (`league_matches`).

- **Picks** are the heroes of a side's five players, so a game without a recorded draft still has them. **Bans** come from the draft (`picks_bans`).
- Per hero and team, each game falls into exactly one of four cases: banned against them, banned by them, picked by the enemy team, or **open**. So a hero is open when neither side banned it and the enemy did not pick it. (Until November 2026 a hero the enemy picked counted as open.)
- **Games played** is the number of games the team picked the hero, **win rate** the share of those it won, and **picked when open** is games played divided by games open.
- A team's **name** is the newest one Steam sent that is not empty.
- A **player's averages on a hero** are the plain means of kills, deaths, assists, last hits, GPM and XPM over the player's league games for this team on that hero.
- A **player's wards** are those of the player's games for this team whose replay is parsed, and those of the player's matches outside the league that have a parsed replay (only a tracked account's matches are ever parsed), within the time and season filters. Each ward says whether it came from a league game, for the heatmap's "Tournament games / Usual matches" dropdown.

### A league player's games outside the league

Shown on the team page under each player, as the same role wheel as a profile's (`dotanalyst/opendota.py`).

- **Source:** OpenDota's list of the player's matches (`/players/{id}/matches`), basic numbers only: hero, side, result, K/D/A, mode, lobby and OpenDota's `lane_role`. The replays of these games are never downloaded or parsed; the poller only wants replays of league games and of tracked accounts' matches.
- **Which games:** the newest 100 (`GAMES`) of the 150 asked for (`ASKED`), after leaving out practice and tournament lobbies (lobby type 1 and 2, league games of any league) and any match stored in `league_matches`. A row without an integer match id, start time, hero and slot, or a true/false result, is dropped.
- **Role:** `lane_role` 1 is the safe lane, 2 mid, 3 the off lane, 4 jungle. OpenDota has it only for games it parsed itself; the others count as "lane unknown".
- **When:** after the replay downloads of each poll, for up to 5 players (`PLAYERS_PER_POLL`) not asked for yet, those of the newest league games first. A player is asked for once and never again, so the list does not grow with the player's later games. A private match history gives an empty list, which still counts as asked. A failed answer leaves the player for the next poll. The Refresh button on a team page first checks for new league games, then asks at once for every player of that team not asked for yet (`refresh_players` in `poll.py`); players already asked for are not asked again.
- The time and season filters do not apply to these games.

### League games as matches

A league game starts out in `league_matches` only; its match page is built from the answer Steam gave for it. It is copied into `matches` when it is younger than 30 days (`MAX_AGE_DAYS`, each poll, so the poller downloads its replay and computes its stats like any match's) or when its replay is asked for (the button on its page, or under "First moves" on a team page). From then on it is a match like any other. No tracked account plays in it, so it joins no account's stats: those only count rows where the account itself played.

### Replay queue (Queue page)

The queue is every match the poller still wants a replay for: `pending`, or `none` and younger than 30 days (`wanted` in `poll.py`, the same condition the poller uses). Each match's next try is now if it was never tried, else an hour (`RETRY_SECONDS`) after its last try, and never earlier than now. The queue is sorted by next try; among matches due now, never-tried ones come first, then the newest. That is the poller's own order, so the first 10 (`DOWNLOADS_PER_POLL`) due matches are the ones the next poll takes. A check by hand ignores the hour and takes the first 10 waiting matches at once.

A replay that is not there yet is put down to one of two causes. "Valve has no file for it" means a salt is known, from the second Steam account or from a cached OpenDota answer. "No salt" means neither source knew the match.

## On the site

Rules that live in the frontend (`frontend/src`), applied to what the API sends.

### Role (Profile)

The lane seen from the player's side: Radiant's safe lane is bottom and Dire's is top, the other side lane is the off lane; mid and jungle are themselves. A match without a parsed replay has no role.

A lane counts as won or lost when `lane_nw_diff` is beyond ±500 net worth, and as even inside that (`EVEN` in `Profile.svelte`).

The role wheel (`RoleWheel.svelte`) gives each lane its share of the middle ring and the heroes played there their share of the outer ring. Clicking a lane in the middle ring turns the wheel in 0.7 s (cubic in-out, at once with reduced motion) until that lane fills the middle ring and its heroes fill the outer one. The number in the centre then counts that lane's matches, and "Show all lanes" turns the wheel back.

### Trend line (Trends)

Each point is the mean of that match's value and of up to 19 parsed matches before it.

### Ward heatmap (Profile, team players)

`lib/WardHeat.svelte`. A density heatmap of the wards the controls let through: toggle buttons for each kind (observers yellow, sentries blue) and each side (as Radiant green, as Dire red), and a dropdown for the ten minutes they were placed in (0–10 … 30–40, and 40 min on; a ward placed before the horn counts to 0–10). On a team player's map a further dropdown picks tournament games, usual matches or both. Observers and sentries are two separate pictures, sentries drawn on top: every ward adds a Gaussian hill with σ = 1.5 map cells (wards on one spot run into one hill, wards a few cells apart stay apart) to its kind's grid of half cells. The height h is coloured at √(h / highest h of that kind), observers along a ramp from dark red through orange and yellow to near white, sentries from dark blue through light blue to near white, so a spot warded once stays visible beside one warded thirty times; below h = 0.05 the map shows through, and up to h = 0.3 the colour fades in. The map under it is darkened. Hovering a 2-cell square tells how many observers and sentries were placed in it. The profile's map covers the matches the profile shows (the last 25 or 100).

### First moves (team page)

`lib/Openings.svelte`. For the team's 6 newest games on one side (`GAMES`; a dropdown picks Radiant or Dire, at first the side of their newest game), the positions of its five heroes from −1:30 to 0:30, read from each game's raw log, drawn as one line per hero. Buttons beside the map switch each game on and off, or all of them on again. A step of more than 8 cells in a second is a teleport and breaks the line. A game without a parsed replay is not drawn.

### Map geometry

`lib/MiniMap.svelte`. The map image covers cells 64 to 191, so a position sits at x − 64 from the left and 191 − y from the top, in cells. Positions outside are drawn on the edge. Checked by laying the hero positions of 30 replays over the image.

Buildings are drawn at fixed places: for each, the centre of the circle melee heroes stand on while hitting it, fitted over 228 replays.

On the overview map of a match, a hero is drawn on its lane at the place laners of its side usually stand (the median over 60 replays, `LANE_SPOTS` in `Match.svelte`), not where it was.

A close-up (a fight, a death) shows the square that holds its places with 8 cells of room around them, at least 48 cells wide.

### Playback

`lib/Playback.svelte`. Positions come once a second. Between them a hero moves on a Catmull-Rom curve through its positions; a move of more than 8 cells in a second (teleport, blink, respawn) is shown as a jump.

### Item timeline (Builds)

Consumables, wards and recipes are left out (`UNLISTED` in `Match.svelte`). A part bought after 0:00 that was built into a bigger item within 60 seconds is left out too, so a finished item does not sit on a pile of its parts.

### Lead charts

A team's lead is Radiant's sum minus Dire's, per minute. The laning table and lane charts use minute 10, or the last minute of a shorter game.
