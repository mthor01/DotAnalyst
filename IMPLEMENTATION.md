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

All of this is in `dotanalyst/derive.py` and is stored in the derived tables. `dotanalyst recompute` builds them again match by match, newest first, so a changed rule reaches old matches by running it. A match keeps its old rows until it is redone, so the site stays filled while it runs (about an hour for 2,300 matches); only a table whose columns changed is thrown away first.

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

### Twin gates

Read from: the combat log's buff events. A hero who starts a twin gate warp gets the buff `modifier_twin_gate_warp_channel`; it ends when the channel finishes and the hero is moved, or sooner when they cancel or are stunned.

- A trip counts when the buff stood at least 4 seconds (`GATE_CHANNEL`), at the second it ended. In 60 replays the 470 buffs lasted 0 s ×15, 1 s ×20, 2 s ×11, 3 s ×7 and 4 s ×417, so nothing sits between a cancelled channel and a full one.
- The `twin_gate_portal_warp` ability event is not used: it marks the start of a channel, cancelled ones included.
- `player_minute.twin_gates` holds the trips up to each minute.

Known limit: a channel that ends in the same second as a stun after 4 seconds counts, although the hero may not have been moved.

### Healing

Read from: the combat log's heals whose source and target are both heroes. Illusions as targets are left out.

A heal counts when the healer and the healed hero are on the same team and are **not the same hero**. What a hero heals itself (regeneration from items, lifesteal) is not counted, since November 2026: it says how the hero lasted, not what it did for the team.

`player_minute.healing` is the sum up to each full minute; `teamfight_players.healing` the sum inside a fight's window.

Known limit: a heal from a summoned unit is not credited to its owner.

### Hero damage per minute

Not worked out: `player_minute.hero_damage` is the replay's own running count from the interval of each full minute. The damage inside a teamfight is added up from the combat log instead (see Teamfights), so the two do not have to agree.

`player_minute.damage_taken` is worked out: the combat log's damage hits on the player's hero by an enemy hero (not an illusion target, attacker credited as for teamfights) up to that minute, after armour and resistances. On the sample replay a side's total dealt by this count equals the other side's total taken, and a hero's dealt damage matches the replay's own `hero_damage`.

### Camps stacked

Not worked out: the replay's own count from the interval.

### Purchases and what they were built into

Read from: the combat log's purchases, and the `recipes` table (item → components, from dotaconstants).

The log reports a finished item as a purchase of its own at the moment its parts come together. For each such item, every component of its recipe uses up the newest earlier purchase of that component by the same player that is not used up yet; that purchase gets `built_at`, the time of the finished item.

Power Treads take a Band of Elvenskin or a Robe in the place of the listed Belt of Strength.

Known limit: a part an ally bought is not found, so the part of the buyer stays an item of its own.

### Skill points

Read from: `DOTA_ABILITY_LEVEL` events.

- At the second a hero appears, the log lists all its abilities and talents, in slot order. That list is not a point spent, but it says which abilities are the hero's own. Any other ability is skipped: a spell Rubick stole, an outpost, a lamp, a twin gate. So is any line with a level below 1.
- Abilities that level together, in the same second at the same level, are one point: the three Shadowrazes, Onslaught and its Release, Fire Spirits and their Launch. The point keeps the ability the hero listed first, the main one.
- An ability named `special_bonus_*` is a talent, except `special_bonus_attributes`, which is a point put into the attributes and shown as a skill point. A talent costs no point of its own.
- A hero gets one point per level. A point beyond the hero's level is an ability that Aghanim's Scepter or Shard gave (Rock Throw, Ice Spire, Fireball) and is skipped. The interval's level can lag a level-up by a few seconds, so the highest level of that second and the 5 after it counts.

The hero's level beside each point is the level in the interval of that second, but at least the number of points spent so far; beside the nth talent, at least 5 + 5n.

Known limit: an ability from Aghanim's or Shard that comes while the hero still has a point unspent takes that point's place in the list. Checking the items bought would fix it; it is rare.

### Buildings

Read from: the combat log's deaths of units named `npc_dota_goodguys_…` or `npc_dota_badguys_…` that are a tower, a barracks or the Ancient. The filler buildings in the bases are left out.

The two tier-4 towers of a side share one name. The first of them to fall is drawn as the one listed first in `MiniMap.svelte`; the log does not say which it was.

### Tormentors

Read from: `CHAT_MESSAGE_MINIBOSS_KILL`, the game's own message, whose `value` names the side that killed it (2 Radiant, 3 Dire). The combat log is not used: it names a summon or an illusion when one landed the blow.

- **Enemies dead:** heroes of the other side whose life state is dying or dead (1 or 2) in the interval of that second.
- **Lead:** Radiant's net worth minus Dire's in the interval of that second (`Log.lead`).

### Wisdom runes

Read from: `CHAT_MESSAGE_RUNE_PICKUP` with `value` 8, and the positions of the intervals. The replay has no event for a rune appearing, so a rune is assumed at each spot every 7:00 of game time (`WISDOM_EVERY`), from 7:00 to the end. The two spots are fixed (`WISDOM_SPOTS`, in replay cells): the one in Radiant's half and the one in Dire's.

- **Taken:** the first wisdom pickup from the rune's time until the next rune's, by a hero alive within 10 cells (`WISDOM_REACH`) of that spot then. A rune nobody picked up stays untaken.
- **Heroes who came:** every hero alive within 10 cells of the spot at any second from 20 seconds before the rune (`WISDOM_BEFORE`) until its pickup, or for 30 seconds (`WISDOM_WAIT`) when nobody took it.
- **Lead:** Radiant's net worth minus Dire's at the second the rune appeared.
- **Deaths at the rune:** every scoreboard death (see *Deaths*) within 10 cells of the spot, from 20 seconds before the rune until 15 seconds (`FIGHT_GAP`) after its pickup, or after the 30 seconds when nobody took it. The extra 15 seconds catch the fight that follows a pickup. A death without a position does not count.

Known limits: a hero who passes the spot in those seconds counts as coming for the rune. The 10 cells are a guess at "at the rune", not checked against how teams play it.

### Positions

Not stored. `positions()` reads the intervals of a time span from the raw log when a page asks (`GET /api/matches/{id}/positions`): ten rows a second for every match would be too much to keep for views that are rarely opened.

## Metrics

One function each in `dotanalyst/metrics.py`, stored per player and match in `metrics`. A metric that does not apply has no row, so averages cover only the matches where the number means something.

| Metric | Rule |
|---|---|
| `lane_cs_diff`, `lane_nw_diff`, `lane_dn_diff` | Last hits (net worth, denies) at 10:00 of all heroes of the player's side in the player's lane, minus the same sum of the enemies in that lane. No value for a jungler, for a lane without enemies, or in a match shorter than 10 minutes. Both players of a lane get the same value |
| `last_hits_at_10`, `denies_at_10`, `net_worth_at_10`, `xp_at_10`, `damage_at_10`, `damage_taken_at_10` | The player's own number in the 10:00 minute row (`hero_damage`, `damage_taken`). No value in a match shorter than 10 minutes |
| `lane_damage_at_10`, `enemy_lane_damage_at_10` | Hero damage by 10:00 summed over the player's side in the player's lane, and over the enemies in that lane. Same lanes and same gaps as `lane_nw_diff`. The enemies' damage counts on any hero of the player's side, so a rotating mid or support taking hits in the lane counts too |
| `kills_by_10`, `deaths_by_10` | The player's kills and deaths before 10:00, from the deaths list. No value in a match shorter than 10 minutes |
| `obs_placed`, `sen_placed` | Wards of that kind the player placed |
| `obs_bought`, `sen_bought` | Wards of that kind the player bought (`ward_observer`, `ward_sentry` purchases). A `ward_dispenser` purchase is the game merging or splitting wards already bought and is not counted. Known limit: wards a teammate bought and handed over count for the buyer, not the one who placed them |
| `wards_destroyed` | Enemy wards of either kind the player destroyed |
| `obs_lifetime` | Mean seconds the player's observers stood. One still standing at the end is left out |
| `camps_pulled_by_10` | Camps pulled before 10:00: the player's number in the 10:00 minute row. No value in a match shorter than 10 minutes. Lotuses collected (`player_minute.lotuses`) and twin gate trips (`player_minute.twin_gates`) are stored but not a metric |
| `camps_stacked` | Camps stacked in the whole match: the player's replay count (see Camps stacked) in the last whole minute row, so a stack in the final partial minute is missed. No value without a minute row |
| `fight_participation` | Share of the match's teamfights the player took part in |
| `kill_participation` | (kills + assists) / kills of the team, from the scoreboard |
| `deaths_outside_fights` | Deaths outside every fight window |

Known limit: the lane differences describe the lane, not the player, and a lane of two against one compares two heroes' sums with one hero's.

## From the scoreboards

In `dotanalyst/queries.py`. Nothing here is stored; it is counted on each request.

### Filters: time and tournament

Every account page and every team page take a time span; a team page also takes a tournament (the Tournament dropdown, `season` in the code), account pages lobby and mode. The Profile and the Player comparison show no Tournament dropdown: they take every game the other filters keep (the API still reads `league_id` on account requests).

- **Time** is all time, last month, last 3, 6 or 12 months, or two dates. A span of months starts on today's date that many calendar months back (`monthsAgo` in `App.svelte`) and has no end. The dates are local days and both count: from 1 Nov to 3 Nov is all of the 1st to the end of the 3rd (`between` in `queries.py`).
- **Tournament** is one of the tracked tournaments (see Tracked tournaments). A match belongs to it when `league_matches` has it under that league id, so on an account page a tournament shows only league games the account itself played.
- A known team without a game in the filters gets an empty page, not "unknown team".
- The team pages keep their own time and season (`times` in `App.svelte`), apart from the account pages: a season picked on a team page does not narrow the profile, and the other way round. Both are kept until the page reloads.

### Played with a tracked account

Steam's data does not say who queued together. A match counts as "with tracked players" when another active tracked account was on the same team.

### Adding a profile (Add profile in the header)

`POST /api/accounts` takes the Dota account id (the friend id) or the 64-bit Steam id; a number of at least `STEAM_ID_BASE` (76561197960265728) is a Steam id and has that subtracted. What is left must lie between 0 and the anonymous id (`ANONYMOUS`, 4294967295), both excluded, or the answer is 422. The browser sends the id as text, as a Steam id is too long for a JavaScript number. An account tracked before and removed is tracked again with its stored matches. The account's Steam picture and, when it has no name, its Steam name (`personaname`) are asked for at once (`store_avatars`, up to 100 accounts per call), so the Account menu shows them right away; if Steam does not answer, the poller asks again on its next round. The matches are not fetched at once: the poller reads them on its next round. Add frequent teammates does the same for every player it adds.

The match page's scoreboard shows each player's name after the hero: the account's label, else its Steam name. A tracked player's name links to their profile (`#account/{id}`); any other player with an account gets a + button that adds them as above. The Steam names of a match's players are asked for once, when the match is first opened (`store_names`), and kept in the player names table; a player Steam has no profile for is asked again at every opening. Anonymous players show as Anonymous.

### Frequent teammates (Profile, Add frequent teammates)

`frequent_teammates` in `queries.py`: every player on the account's team in at least 10 (`TEAMMATE_GAMES`) of its newest 500 (`TEAMMATE_MATCHES`) stored matches, whatever the page's filters. Anonymous players are left out. The button tracks those not tracked yet, as Add profile does, and says how many it added.

Known limits: only stored matches count, so an account added a minute ago has none until the poller has read them; a player with a hidden account in some games counts only the games where it was public.

### Solo or party

Whether the player queued alone or with others (`_parties` in `queries.py`, the `party_size` of a match row, 1 for solo), which the Queue filter of the filter panel keeps:

1. **OpenDota's party size** where it is known: above 1 is a party, and the Matches tab shows that size. Its answer is only stored for matches whose replay came through OpenDota (for the replay salt); `store_parties` in `derive.py` copies it onto `match_players.party_size` when the match is derived.
2. **Otherwise a guess**: a party when a teammate with a public account was on the player's team in at least 5 (`PARTY_TOGETHER`) of all stored matches; the size shown is 1 plus those regular teammates, so it is a floor (a party member with a hidden account, or one met fewer than 5 times, is not counted). Checked against the matches with a known party size, 3 to 5 gave 87–100 % right, and 5 called no solo match a party.

Known limits: a party of players with hidden accounts looks solo to the guess; someone met often by chance in solo queue makes those matches look like a party; the count is over every stored match, so a filter on time does not change who counts as a regular teammate.

### Position 1–5 of a player

Every row of an account's match list carries the player's position, 1 (carry) to 5 (hard support), worked out per team on each request (`positions` in `queries.py`).

- **Lane** is the lane from the replay (see Lane of a player), seen from the team's side: the safe lane is bottom for Radiant and top for Dire.
- **Farm** is the scoreboard's last hits at the end of the match; equal last hits go by net worth.
- The safe lane's most farmed player is 1 and its least farmed 5, the mid is 2, the off lane's most farmed 3 and least farmed 4. A player alone in the safe or off lane gets only the first of those (1 or 3).
- Everyone else (a jungler, a third player in a lane, a lane the replay could not tell, every player of a match without a parsed replay) takes the positions still open, the most farmed the lowest.

Checked: the 7 tracked accounts' matches give each account one or two clear main positions; for the parsed ones, supports come out 4 and 5 and cores 1 to 3 (November 2026).

Known limits: without a parsed replay (most matches) the position is only the team's farm order, so a mid who out-farms the carry is 1 and the carry 2, and a support with a big late game can rank above a core. With a replay, a support who lanes alone and a core who jungles take the open places by farm, which can swap 4 and 5 with 1 or 3.

### Tracked tournaments (Tournaments page)

The tracked tournaments are the `leagues` table, league id to name. A new database tracks none. The add form on the Tournaments page takes a league id; the name is OpenDota's (`/leagues/{id}`), or "League {id}" when OpenDota has none or does not answer. The league sync reads every tracked tournament, so a new one is read in full on the poller's next round for league games, up to Steam's newest 500 games of a league.

The list gives per tournament its stored games, the teams that played in them (a side without a team is none), and the start of its first and last stored game. The Teams tab of the page is the League teams list.

### League teams

Built from the drafts and scoreboards of the league games (`league_matches`).

- **Picks** are the heroes of a side's five players, so a game without a recorded draft still has them. **Bans** come from the draft (`picks_bans`).
- Per hero and team, each game falls into exactly one of four cases: banned against them, banned by them, picked by the enemy team, or **open**. So a hero is open when neither side banned it and the enemy did not pick it. (Until November 2026 a hero the enemy picked counted as open.)
- **Games played** is the number of games the team picked the hero, **win rate** the share of those it won, and **picked when open** is games played divided by games open.
- A team's **name** is the newest one Steam sent that is not empty.
- A team's **logo** is the `radiant_logo` / `dire_logo` of its newest league game where it is not 0, whatever the filters. That number is a Steam UGC id; Steam's `GetUGCFileDetails` turns it into the image's address. Each answer, an address or Steam's 404 for an unknown id, is kept in `data/logos.json` and never asked for again; a failed request is asked again on the next page load. Without a Steam key or an answer the page shows no logo.
- A **player's averages on a hero** are the plain means of kills, deaths, assists, last hits, GPM and XPM over the player's league games for this team on that hero.
- A **player's wards** are those of the player's games for this team whose replay is parsed, and those of the player's matches outside the league that have a parsed replay, within the time and season filters. Refresh on the team page marks its players (`replays_wanted` on their game list); from then on each round of the usual-games step turns up to 10 of their usual games from the last 90 days that are not stored yet into matches, newest first, from OpenDota's answer (kept in `data/opendota/`, so the replay download asks no second time), and their replays are fetched like any other. A game OpenDota does not know is not asked for again until the poller restarts. Under a marked player's map, the page says how many of their usual games from the last 90 days still wait for a replay (`usual_waiting`); older usual games are never fetched, as Valve drops replays after about 100 days and the queue would never end. Each ward says whether it came from a league game, for the heatmap's "Tournament games / Usual matches" dropdown.
- The **team's wards** (the map on the General tab) are every player's wards from the team's league games whose replay is parsed, without their usual matches; the games the slider's share is taken of are those parsed league games.
- **Tormentor**, **wisdom runes** and **roles in their draft** only count the team's league games whose replay is parsed. They are seen from the team's side, so a lead is the team's net worth minus the enemy's.
  - **Tormentor:** only each game's first Tormentor (the earliest kill) counts. Per game: when it fell, which side took it, how many of the other side's heroes were dead at that moment, and the net worth lead of the side that took it. The General tab splits them into the ones the team took and the ones the enemy took, each with its averages, so "lead" there is the taker's lead.
  - **First blood:** the first hero death of the game that is not a deny (killer on the dead hero's own side). The side that did not lose the hero gets it, so a hero killed by creeps, a tower or neutrals gives first blood to the other side. The percentage is over the parsed games.
  - **Lanes:** each side's net worth and experience summed per physical lane (top, mid, bottom) at 10:00 (`LANE_MINUTE`), with the lanes of *Lanes* above; jungle and roaming heroes count to none. A lane counts in a game only when both sides had a hero in it. The team's safe lane is bottom as Radiant and top as Dire, the off lane the other one. Per lane the page shows how many games counted, how many the team was ahead in net worth (lead above 0), and the average net worth and experience lead.
  - **Wisdom runes:** split into the rune in the team's half and the one in the enemy's. The team **contested** a rune when at least one of its heroes came to it (see *Wisdom runes* above). Heroes and lead are averaged over the contested ones; taken counts every rune the team picked up. **Kills** and **deaths per game** are the enemy's and the team's deaths at the rune, summed over every rune of that half, contested or not, and divided by the parsed games.
  - **Roles in their draft:** the team's picks from `picks_bans` in draft order, 1st to 5th. Each hero is matched to the team's player on it, and the count goes to that player's position in the game (*Position 1–5 of a player*). In Captains Mode a team picks once in the first phase, three times in the second and once in the last (checked on the stored drafts, November 2026). A game without a recorded draft adds nothing.

### Main stack and stand-ins (team page, Overview tab)

- **Main stack:** the five players who played in the most of the team's newest 10 league games (`RECENT` in `queries.py`) shown on the page, so the time and season filters apply. A tie goes to the player whose latest game for the team is newer. Only players in at least one of those 10 games can be in it, so a team with fewer than five such players shows a smaller stack.
- **Stand-ins:** every other player who played for the team in the filtered games within the last 3 months (`STAND_IN_MONTHS` in `Team.svelte`, counted back from today, not from the team's last game), newest last game first.
- **Historical players:** the other players whose last game for the team in the filtered games is older than that, in the same order. A team that has not played for 3 months has only historical players.
- **Position:** every player of the page, stack, stand-ins and historical players alike, shows the position 1–5 they took most often for the team in the filtered games (`team` in `queries.py`). Per game it is the replay's position where the game is parsed (see Positions), else `positions` (see Position 1–5 of a player) over the team's five, with the lane from OpenDota's `lane_role` where the league answer has one. Equal counts go to the position of the player's newest game.
- Each member's bar fills one step per game of those 10 they played. Per player the page also shows all their games for the team and their three most played heroes.
- **Pictures:** the Steam profile picture (`avatarmedium` of `GetPlayerSummaries`), kept in `player_names.avatar`. The league sync asks for it together with a new player's name, and once for players whose name was stored before pictures were (`avatar` still NULL). `""` means Steam sent no picture or has no profile for the id, and the player is not asked again. Without a picture, a tracked account's own picture is used, else the name's first letter.
- **Links:** a player who is a tracked account opens that account's profile on this site (`#account/<id>` picks the account, then becomes `#profile`). Anyone else opens their OpenDota page in a new tab.
- The Overview's other numbers: the record overall and per side, the first blood share (as on the General tab, over parsed games), and the results of the newest 10 games, oldest to newest.

### A league player's games outside the league

Shown on the team page under each player, as the same role wheel as a profile's (`dotanalyst/opendota.py`).

- **Source:** OpenDota's list of the player's matches (`/players/{id}/matches`), basic numbers only: hero, side, result, K/D/A, mode, lobby and OpenDota's `lane_role`. The replays of these games are never downloaded or parsed; the poller only wants replays of league games and of tracked accounts' matches.
- **Which games:** the newest 100 (`GAMES`) of the 150 asked for (`ASKED`), after leaving out practice and tournament lobbies (lobby type 1 and 2, league games of any league) and any match stored in `league_matches`. A row without an integer match id, start time, hero and slot, or a true/false result, is dropped.
- **Role:** `lane_role` 1 is the safe lane, 2 mid, 3 the off lane, 4 jungle. OpenDota has it only for games it parsed itself; the others count as "lane unknown".
- **When:** by the players step of the poller (see Poll steps below), for every player not asked for yet, those of the newest league games first. OpenDota's calls of every step share one pacer (`pace` in `opendota.py`): one a second, its limit of 60 a minute, whichever thread calls. A player is asked for once and never again, so the list does not grow with the player's later games. A private match history gives an empty list, which still counts as asked. A failed answer stops the round; the player is asked again in the step's next round, 10 seconds later. The Refresh button on a team page first checks for new league games, then asks at once for every player of that team not asked for yet (`refresh_players` in `poll.py`); players already asked for are not asked again.
- The time and season filters do not apply to these games.

### League games as matches

A league game starts out in `league_matches` only; its match page is built from the answer Steam gave for it. It is copied into `matches` when it is younger than 90 days (`MAX_AGE_DAYS` in `replay.py`, 30 until 2026-11-20, by the leagues step every round, so the poller downloads its replay and computes its stats like any match's) or when its replay is asked for (the button on its page, or under "First moves" on a team page). From then on it is a match like any other. No tracked account plays in it, so it joins no account's stats: those only count rows where the account itself played.

### Replay queue (Queue page)

The queue is every match the poller still wants a replay for: `pending`, or `none` and younger than 90 days (`wanted` in `poll.py`, the same condition the poller uses). Each match's next try is now if it was never tried, else 10 seconds (`RETRY_SECONDS`) after its last try, and never earlier than now. The downloads step looks for due matches every 10 seconds too, so a waiting match is tried again about every 20 seconds; for a match without a known salt, each try costs one OpenDota call (the pacer keeps all of them under 60 a minute). The queue is sorted by next try; among matches due now, never-tried ones come first, then the newest. That is the order the downloads step starts them in, 4 (`WORKERS`) downloading and parsing at a time, so they can finish in another order; each time one finishes, the next due match takes its place, including one that became due meanwhile.

A replay that is not there yet is put down to one of two causes. "Valve has no file for it" means a salt is known, from the second Steam account or from a cached OpenDota answer. "No salt" means neither source knew the match.

The Whose column names the tracked accounts that played the match (their label and Steam picture), the checked league players it is a usual game of (their stored name, or their id when none is stored), and the tournament it was played in (its tracked name, or "League {id}") (`whose` in `poll.py`).

### Poll steps (Queue page)

The poller is eight steps, in `STEP_FUNCS` in `poll.py`: new matches of the accounts, new league games, usual games of checked players, replays in the Dota client folder, replay ids (salts) from Valve, replay downloads and parsing, game lists of league players, stats of parsed matches. Since 2026-11-20 each runs on a thread of its own (`start`, called when the server starts), side by side, none waiting for another: a round does all the work the step finds, then the step looks again 10 seconds (`LOOP_SECONDS`) after that round ended. So downloads start right after a restart, while the accounts step is still reading Steam, and a match the accounts step stores is picked up by the downloads step within 10 seconds. Before, one poll ran the steps in order every minute.

- **Rules that keep the steps apart.** Each round has its own database session and HTTP client. A match a step downloads, parses or computes is claimed in `WORKING` (`claim` / `release`): another step, or the site's Request replay, leaves a claimed match alone. Each step and the button that does the same work by hand (`refresh`, `refresh_leagues`, `refresh_players`) share a lock, so they never run at once. SQLite lets one writer at a time; a step waits up to 30 seconds for another's write (`timeout` in `db.py`).
- **Rate limits across threads.** OpenDota's calls share one pacer, one a second; Steam's calls share another (`pace` in `steam.py`), one a second. `salts.json` is written to a temporary file and swapped in whole, since the downloads step reads it while the salts step writes it.
- **Downloads:** every due match (see the replay queue above), one at a time (`WORKERS`) on a worker thread that touches no database; the step's own thread records each result. One, not more: Valve's replay servers are Google's CDN in front of storage, and it cuts off a download it passes straight through from storage once it runs past about 45 to 80 s (measured November 2026, at about 0.5 MB/s per download). Parallel downloads share the line, so each runs longer and more of them get cut. The Queue page shows the download under way and the last 10 that ended, each with its speed in compressed MB/s and whether it was cut off (kept in memory only). A download Valve cuts off midway (`RemoteProtocolError`, `ReadError`; about half of them in November 2026) only puts that match back to pending for its retry, and the freed worker takes the next match. Any other server or disk error cancels the downloads not yet started; they wait for the next round. A due match whose complete replay is in the Dota client folder is left to the folder step.
- **Salts:** the second Steam account is asked for at most 10 (`SALTS_PER_POLL`) due matches a round whose salt neither it nor OpenDota gave yet, since Valve allows it about 100 a day. Each match is asked for once a run (`ASKED`, in memory), whatever the answer, so a failing login does not cost a try every 10 seconds; the downloads step asks OpenDota for the rest.
- **Stats:** a match whose stats fail is skipped until the server restarts (`NO_STATS`), so it is not retried every 10 seconds.
- `poll_once` runs the eight steps once, one after another, on the caller's thread; the tests use it.

The Queue page lists the steps with:

- **Activity**: a step with work right now is marked "running", with what it does, since when, and how far it is (`RUNNING`, which each step fills while it works and empties when its round ends). The downloads step names the match under way, and its "x of y" is parsed this round of parsed + under way + still due: one that fails or has no replay yet drops out of y. Otherwise when its last round ended (`CHECKED`, set whether the round had work or not) and when the next one starts, 10 seconds after that.
- **Planned**: a bare count of what the step's next round would do, counted now with the poller's own conditions ("12 replays, 1 waiting for a retry"; "off: no STEAM_API_KEY" or "off: no STEAM_ALT_USER" for a step that cannot run). Salts count the due matches Valve was not asked for yet and that have no salt from Valve or OpenDota.
- **Finished**: what the step's rounds finished since the server started (`FINISHED`: `run_step` adds what each round returns; in memory, so 0 after a restart), plus what the round running now has finished so far. Without that, the downloads step, whose one round takes every due match one by one and so can run for hours, would show 0 until its round ends.

The page no longer says why planned work waits (usual games OpenDota did not know, failed stats, old matches left alone, the next retry); the parser being down shows in the Poller card above, and each match's next try in the replay queue.

Known limits: with nothing to do each step still reads the database every 10 seconds, and the accounts and leagues steps ask Steam (about one call per account and per league, paced to one a second). A match stored by the accounts and leagues steps at the same moment can fail one of them with a duplicate key; it is logged and the next round goes on.

Known limit: the league players' count walks every league game on each refresh of the page (about 0.2 s on 2000 games).

### Background progress (bar in the header, Replay column)

`progress` in `poll.py`, behind `GET /api/progress`, which every page reads every 3 seconds. A replay counts as **waiting** under the same condition as the queue (`wanted`: `pending`, or `none` and younger than 90 days), and as **parsed** when its state is `parsed`. Replays the poller gave up on (`unavailable`, `failed`, or `none` older than 90 days) count in neither, so the bar can reach 100 % while such matches remain. The bar shows parsed out of parsed plus waiting over all matches. It is a small bar with its count, in the header between the page tabs and the account; clicking it opens the Queue page, which has no tab of its own. Hovering it (or keyboard focus) opens an overview that adds:

- one bar per **active** tracked account, counting the matches it played in (through `match_players`);
- one bar per tracked tournament, counting its games that are already in `matches` (through `league_matches`). League games still only in `league_matches` are counted in no bar;
- one line per step with work right now (`RUNNING`): a bar with done / total when the step counts its work (usual games, folder replays, downloads, players, stats), else what it is doing.

`WORKING` holds the match ids a step is downloading, parsing or computing right now (`claim` adds the id, `release` removes it when the job ends, failed or not). The Replay column of the match lists shows a spinner ("Parsing…") for those, "⏳ Waiting" for the other wanted ones, "Parsed", or "–". On the team page a league game not yet in `matches` has no state; it counts as waiting while it is younger than 90 days, since the leagues step copies it in within 10 seconds.

Known limit: a list loaded before a replay finished keeps its old state for that row ("Waiting" again once the spinner stops) until the page is reloaded; only the bar and the spinner follow live.

### Storage (Queue page)

`storage` in `poll.py` adds up the size of every file in the data folder by its top-level part: `raw` is the parser output, `dotanalyst.db` with its `-wal` and `-shm` files the database, `opendota` and `steam` the cached API answers, `tmp` the replays being fetched; anything else is Other. Sizes are shown in binary units (1 GB = 2³⁰ bytes), as the file manager counts them. The parts always come in that order with their fixed colour, an empty part included in the table but left out of the donut.

## On the site

Rules that live in the frontend (`frontend/src`), applied to what the API sends.

### Role (Profile)

The lane seen from the player's side: Radiant's safe lane is bottom and Dire's is top, the other side lane is the off lane; mid and jungle are themselves. A match without a parsed replay has no role.

The filter panel right of the page (above it on narrow screens, `App.svelte`) holds every filter, and every tab of the Profile and the Player comparison takes all of them. Role keeps only the matches the account played in one position, or in the cores (1–3) or the supports (4–5) together (see Position 1–5 of a player); Queue keeps solo or party matches (see Solo or party); Hero keeps the matches in which the account played that hero (its own `hero_id`, `conditions` in `queries.py`; whoever else played it does not count); Matches keeps the 25, 100 or 500 newest, or all. The page sends them as `position`, `party` and `last`, and the server applies them in that order after the other filters (`narrowed` in `queries.py`), so the newest 100 are the newest 100 of that role and queue. A team page takes only the time and the tournament (it has no Hero filter). The panel's top line says how many matches the filters select and how many of them have a parsed replay (on a team page: its games); the Player comparison has two accounts and shows no count. On a wide screen the panel starts level with the page under its tabs (measured in `App.svelte`, so it follows the profile's title) and stays in view while scrolling. On the Overview hero table and the Heroes tab the match count draws a bar beside the number, full for the most played hero of the table. A row of the Overview hero table opens the Heroes tab with that hero unfolded. The Heroes tab sums the same matches the Matches tab lists, per hero, in the page (`Heroes.svelte`): games, win rate, average K / D / A, GPM, XPM, LH / DN and duration, the positions played (by how often, from the position each match row carries), and when it was last played (today, yesterday, N days ago, a date past 30 days). Every column but Hero and Roles sorts; a tie goes to the hero with more games, so 3 of 3 won ranks above 1 of 1. The At least 1+ / 3+ / 5+ buttons hide heroes with fewer games. A row unfolds wherever it is clicked, into the hero's most common items (the final six slots of each match, an item counted once per match, the eight most frequent with how many of its games had them) and every match on that hero, newest first, in the Matches tab's table: each of them unfolds into the match too. That list has no day groups, since one hero's matches are too few for them. A row of the Matches tab, and a game on a team page, unfolds into the match wherever it is clicked, except on its links and buttons; the arrow at its right end opens the match page.

The Matches tab (`Matches.svelte`) lists the filtered matches 50 at a time, with a button for 50 more; a new set of matches starts again at 50. A header click sorts by that column (date, K/D/A by (kills + assists) / deaths with at least 1 death, GPM, XPM, last hits, duration), a second click turns the order round. In date order the rows fall under a header per local day (Today, Yesterday, then the date) with that day's wins and losses, counted over all the selected matches of the day, not only the shown ones; the row then shows the time of day. Beside the hero, the position icon (see Position 1–5 of a player); Party shows the party size (see Solo or party), highlighted when a tracked player was on the team. Items are the six slots in one line, empty ones kept, then the neutral item. Parse is the replay's state: parsed, being parsed, queued, failed, expired (Valve no longer has the replay), or not fetched (the match page can still ask for it).

A lane counts as won or lost when `lane_nw_diff` is beyond ±500 net worth, and as even inside that (`EVEN` in `api.ts`).

The role wheel (`RoleWheel.svelte`) gives each position 1–5 (see Position 1–5 of a player) its share of the middle ring; on a team page the middle ring is the lanes instead. The outer ring gives each hero its share of all the matches, once, whatever roles it was played in, most played first, tinted green when at least half were won and red otherwise. A slice gets the hero's icon when its arc at radius 78 is at least 17 units (about 3.5% of the matches). Heroes whose slice would be narrower than 5 units at the outer edge (radius 97, about 0.8% of the matches; 4 or fewer of 500), so thin that it reads as a gap, merge into one grey slice at the end labelled "+N", whose tooltip lists them; a single such hero keeps its own slice. Clicking a part of the middle ring folds the wheel in 0.7 s (cubic in-out, at once with reduced motion) until that part fills the middle ring: every part's share moves in a straight line from what is drawn now to its share with the new pick, so the old pick folds while the new one unfolds, straight from one part to another, and a pick made mid-way starts from where the wheel is. The outer ring fades out over the first half and back in over the second with only that part's heroes, under the same rule. The number in the centre then counts that part's matches, named under it in short ("soft support", "cores", "safe lane"); the "Show all roles" button below the wheel folds it back. The button is always there, only hidden while the whole wheel shows, so the card keeps its height when it comes and goes. On the profile the middle ring and the filter panel's Role are one choice: a click sets the Role filter, and setting Role (one position, Cores or Supports, which zoom over their range together) turns the wheel the same way. The rings there come from the matches without the Role filter (a second request, the same filters minus `position`), so every role stays on the wheel; the centre count and the zoomed outer ring come from the filtered matches. A picked role with no matches in that unfiltered set leaves the middle ring as it is.

The wheel has no legend (on the profile and on team pages): each part of the middle ring carries its role's icon instead (`public/roles`: a sword for pos 1, a bow for pos 2, a shield for pos 3, a hand with a flame for pos 4, a hand with sparkles for pos 5; on team pages the safe, mid and off lane take the pos 1, 2 and 3 icons, the jungle shows two trees and an unknown lane a "?"). An icon is 16 units across, smaller where the part's arc at radius 38 (the icon's inner edge) is shorter, less 2 units of margin, and left out under 6. Each part's and hero's numbers are in its hover title. The wheel is at most 380 px wide.

### Form (Profile)

The Overview cell "Form", right of Activity: the newest 15 of the filtered matches (`FORM` in `Profile.svelte`) as the icons of the heroes played, oldest first, in one row in the middle of the cell's height, each over a disc, a green "W" won and a red "L" lost, and each a link to its match page. The header counts the wins and losses of the matches shown ("6 W 9 L").

### K / D / A (Profile)

The Overview card in the top row: the mean kills, deaths and assists over the filtered matches. The top row shows only the numbers, with no line under them; the lanes card names its rule (even is within ±500 net worth at 10:00) when hovered.

### Activity (Profile)

On the Overview tab: the account's games per day over the last 6 months, one square per day and a column per week from Monday (the first column starts on the Monday of the week 6 months ago). The matches of the filter panel count, so with 25 newest only those 25 show. A day with games gets a circle whose area is in proportion to its games (the busiest day 81 % of its cell's width across, at least 30 %) and whose colour is its win rate: yellow (`--series-4`) at 50 %, mixed in OKLab towards red (`--dire`) below it and green (`--radiant`) above it, in proportion to the distance from 50 %: full red at 25 % or less, full green at 75 % or more. Days are the browser's local days. When the filters change, each circle grows, shrinks and changes colour in 0.45 s, a week column 12 ms after the one left of it, so the change sweeps from the oldest week to the newest (at once with reduced motion). The cell sits under the role wheel and is as wide (the Overview's two columns share 9 : 11). The day cells are square and share the cell's whole width (the page's max width keeps them near 20 px), 7 px at least; the circle's size is a share of the cell's width. Where 7 px cells still don't fit, the calendar scrolls and opens at its newest week. Every second weekday is labelled (Mon, Wed, Fri, Sun).

### Ward heatmap (Profile, team players, Player comparison)

`lib/WardHeat.svelte`. A density heatmap of the wards the controls let through: one set of buttons picks both kinds or one (observers yellow, sentries blue), another both sides or one (as Radiant green, as Dire red), both and both at first. A timeline under the map has a toggle per ten minutes the wards were placed in (0–10 … 30–40, and 40+; a ward placed before the horn counts to 0–10), all on at first, any number on at once, and one button that turns them all on, or all off when they all are on. A dropdown keeps wins, losses or both (whether the warding player's side won that game). On a team player's map a further dropdown picks tournament games, usual matches or both. Observers and sentries are two separate pictures, sentries drawn on top: every ward adds a Gaussian hill with σ = 1.5 map cells (wards on one spot run into one hill, wards a few cells apart stay apart) to its kind's grid of half cells. The height h is coloured at √(h / highest h of that kind), observers along a ramp from dark red through orange and yellow to near white, sentries from dark blue through light blue to near white, so a spot warded once stays visible beside one warded thirty times; below h = 0.05 the map shows through, and up to h = 0.3 the colour fades in. The map under it is darkened. Hovering a 2-cell square tells how many observers and sentries were placed in it, and in how many of the chosen games. The profile's map covers the matches the profile shows (the last 25, 100 or 500, 100 at first, of the role picked).

A horizontal slider under the timeline, the "Quantity filter" (its tooltip gives the exact rule), keeps only the 2-cell squares warded in at least its share of the chosen games, from 0 % (every warded spot) to 50 % in steps of 1 %: a square counts each game once, however many wards went into it. The chosen games are the parsed games of the sides the buttons pick and the result the wins/losses dropdown picks (and, on a team player's map, of the tournament/usual dropdown), games without any ward included; the timeline picks wards, not games, so it does not change how many games there are. The profile passes its parsed matches, a team player their parsed games (`parsed` in the team endpoint). Known limit: the squares are a fixed grid, so a spot warded on both sides of a square's edge is split between two squares and can fall below a share that it passes as one.

### Player comparison

`Compare.svelte`. Two accounts side by side, each under its profile picture and name; the name is a dropdown that picks another tracked account. Down the middle run the stats, each account's number on its side: matches, win rate, kills, deaths, assists, gold and experience per minute (means over every match the filters keep), parsed matches, and the means of the Metrics (over each account's parsed matches). Of the two numbers the better is green and the worse red; less is better for deaths and deaths outside teamfights, more for the rest. Two numbers that show the same, a missing one, and the two counts (matches, parsed matches) stay uncoloured. Under them the line of how often the two were on the same team counts every stored match. Then the two accounts' ward heatmaps (see Ward heatmap), each over its parsed matches, the first account's on the left and the second's on the right, with one control panel between them: the side and kind buttons, the result dropdown, Reset view, the timeline, the quantity filter and the "?" that explains the map. There is no colour legend: the kind buttons carry the colours. The maps show only the picture and their ward counts; the panel and a zoom or pan on either map apply to both. Under 1200 px wide the panel sits above the two maps. Known limit: a stat is better or worse without regard to the role, so a support's lower gold per minute shows red beside a core's.

### First moves (team page)

`lib/Openings.svelte`. For the team's 6 newest games on one side (`GAMES`; a button above the map switches between Radiant and Dire, at first the side of their newest game), the positions of its five heroes from −1:30 to 0:30, read from each game's raw log, drawn as one line per hero. Buttons beside the map switch each game on and off, or all of them on again. A step of more than 8 cells in a second is a teleport and breaks the line. A game without a parsed replay is not drawn.

### Map geometry

`lib/MiniMap.svelte`. The map image covers cells 64 to 191, so a position sits at x − 64 from the left and 191 − y from the top, in cells. Positions outside are drawn on the edge. Checked by laying the hero positions of 30 replays over the image.

Buildings are drawn at fixed places: for each, the centre of the circle melee heroes stand on while hitting it, fitted over 228 replays.

On the overview map of a match, a hero is drawn on its lane at the place laners of its side usually stand (the median over 60 replays, `LANE_SPOTS` in `Match.svelte`), not where it was.

A close-up (a fight, a death) shows the square that holds its places with 8 cells of room around them, at least 48 cells wide.

### Playback

`lib/Playback.svelte`. All ten heroes and the wards standing at that moment are always drawn; there is no side filter. Positions come once a second. Between them a hero moves on a Catmull-Rom curve through its positions; a move of more than 8 cells in a second (teleport, blink, respawn) is shown as a jump.

### Map tab (match page)

The wards map and the deaths map each have buttons that pick both sides or one; the wards map also both kinds or one. The deaths map has a row of the ten heroes' icons, and All: a hero picked shows only that hero's deaths.

### Item timeline (Builds)

Consumables, wards and recipes are left out (`UNLISTED` in `Match.svelte`). A part bought after 0:00 that was built into a bigger item within 60 seconds is left out too, so a finished item does not sit on a pile of its parts.

### Draft (match page)

The match's `picks_bans` from Steam's answer, in draft order, so it is there with or without a parsed replay, and missing in modes without a draft (no picks or bans recorded). Only Captains Mode gets a Draft tab; other modes show the pick order on the General tab, under the scoreboard. In Captains Mode it is drawn as the game draws it: Radiant's heroes on the left, Dire's on the right, the turn numbers down the middle, bans smaller and grey. A turn shares its row with the next when the next is the other side's and of the same kind (two bans, or two picks), as the game pairs them. In other modes it is only the bans and the picks numbered in the order they were made, each with a bar in its side's colour. An unfolded game on the team page shows the same draft right of the scoreboard, with "Them" and "Enemy" under the side names; the two boxes are made as tall as the taller one and the draft spreads its rows over that height.

### Averages (Profile Overview)

`Profile.svelte`, the bottom of the Overview (`SECTIONS`): the profile's averages over the filtered matches, in three cards: Economy (gold and experience per minute, camps stacked), Laning at 10:00 (last hit, net worth and deny difference to the enemy lane) and Fights (kill participation, teamfights taken part in, deaths outside teamfights). Results, kills / deaths / assists and the ward numbers are left out: the Overview's top row and the Warding tab already show them. There is no separate General tab any more; an old `#profile/general` link opens the Overview. The numbers are worked out in the page from the match rows (`/api/matches`), which carry the replay metrics as fields (`ROW_METRICS` in `queries.py`); a replay stat is the mean over the matches that have it, so only parsed ones count.

- **Formats:** counts with one decimal, gold and experience whole, shares as whole percents; the lane differences are signed and green above 0, red below.
- **Hover:** how many matches the number is over, their median and the best and worst single game (for stats that are neither better high nor low: the most and fewest), and the same stat over the matches before.
- **Rough numbers:** a stat over fewer than 10 matches (`FEW`) is dimmed, says so on hover and gets no trend. This mostly hits metrics added after most replays were parsed, until `recompute` fills them.
- **Trend:** the same number of matches as shown, under the same filters, from before the oldest one shown (`date_to` the day before it, `last` = that count), fetched only while the Overview is open. A ▲/▼ with the difference shows under the number when the two round differently and both sides have at least 10 matches with the stat; green when it got better, red when worse, grey for neutral stats. Known limit: the API filters by whole days, so other matches on the day of the oldest one shown are in neither set.

### Ward numbers (Profile)

The Warding tab is one card in three columns: three lists on the left, the ward heatmap in the middle, and the map's controls in a column on its right. The controls are a second `WardHeat` (`only="controls"`, bound to the map as on Player comparison). Under 1250 px wide the controls go under the map. Under 900 px it is all one column: the lists, the map, then the controls. Only matches with a parsed replay count.

- **Observers:** bought, placed, placed in all, uptime, dewarded by the enemy.
- **Sentries:** bought, placed, placed in all, dewarded by the enemy.
- **Enemy wards:** destroyed.

The rules:

- **Bought and destroyed:** the mean of that metric (see Metrics) over the parsed matches that have it.
- **Placed:** the account's wards of that kind on the profile's map (`/api/wards`), divided by the parsed filtered matches.
- **Placed in all:** the same wards, counted.
- **Uptime:** the mean of the matches' `obs_lifetime`. A match with few observers weighs as much as one with many. An observer still standing at the end is left out.
- **Dewarded by the enemy:** the share of those wards with `killed` set, meaning an enemy hero, a creep or a building destroyed them (see Wards). A ward that ran out or stood to the end is not dewarded.

The heatmap's own ward count is hidden here (`counts={false}`), since the lists show it. The explanation sits behind the "?" buttons, one by the intro and one at the foot of the controls.

Known limit: placed, placed in all and dewarded follow only the filters the map follows, not the map's own buttons. They count both sides, wins and losses, and every minute, whatever the buttons pick.

### Laning (Profile)

The Laning tab: the means of the 10:00 metrics (see Metrics) over the profile's matches, with the role and count picker above it; a line at its top says so, with the count of matches that have a 10:00 row. One hero is the filter panel's Hero filter, as on every other tab. Two cards of lists, each row a label on the left and its number on the right; only the line at the top names the time, so no title repeats it. The first card holds three lists of equal width (stacked under 700px): Farm, Fights and Lane result vs game result (below). Farm: last hits, denies, net worth and experience at 10:00 and camps pulled before 10:00 (`camps_pulled_by_10`). Fights: kills and deaths before 10:00 and your own hero damage dealt (`damage_at_10`) and taken (`damage_taken_at_10`). The second card puts Your lane vs the enemy lane beside the lane strip: `lane_nw_diff`, `lane_cs_diff` and `lane_dn_diff` (green above 0, red below), your lane's hero damage (`lane_damage_at_10`) and the enemy lane's (`enemy_lane_damage_at_10`). The strip, Net worth lead per match: one column per match shown, oldest on the left, with a bar for `lane_nw_diff` (up when ahead, scaled to the biggest lead, at least 1000) and a dot for the result. Then the best and worst lanes, ranked by `lane_nw_diff`, with `lane_nw_diff` and `lane_cs_diff` in their lead columns. Each mean covers only the matches that have that metric, so a lane stat leaves out jungle games while the farm stats keep them; the count in that top line is of the matches with a 10:00 row.

Best lanes, then worst lanes: single matches, not averages. The matches shown that have the chosen net worth lead are ranked by it; best lanes are the 5 highest, worst lanes the 5 lowest, worst first. With fewer than 10 such matches best lanes take the top half (rounded up) and worst lanes the rest, so no match is in both. Each row gives the date (a link to the match page), Your heroes (yours, then `lane_allies`: your team's other heroes in your lane), Enemy heroes (`lane_enemies`: the other team's heroes in it), the result, both leads and `deaths_by_10`. Both hero columns always show the whole lane as portraits; a match without lanes (no replay, or you were outside top, mid and bot) shows only your hero. Both tables share fixed column widths, so their columns line up; a row unfolds into the match (as on the Matches tab) wherever it is clicked, except on the date link, which opens the match page.

### Lane result vs game result (Laning)

How often the game was won after a won, an even and a lost lane: the matches shown that have `lane_nw_diff` fall into won (above +500 at 10:00), even (within ±500) and lost (below −500), the same `EVEN` rule as everywhere, and the list gives a row per kind (Won lane, Even lane, Lost lane): the share of them won as a win-rate bar from the 50% line, then the count ("17 / 41"); a kind with no matches shows a dash. Matches without a lane lead (no replay, jungle, no 10:00 row) are left out.

### Lead charts

A team's lead is Radiant's sum minus Dire's, per minute. The laning table and lane charts use minute 10, or the last minute of a shorter game.
