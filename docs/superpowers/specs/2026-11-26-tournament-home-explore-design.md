# Tournaments home and a richer Explore

## Intent

The Tournaments section opens on Explore today, with Search and Subscribed as separate tabs. Explore is two plain
tables (leagues live now, biggest of the last 30 days). The user wants:

- **Search as the home page** of the Tournaments section, showing their subscribed tournaments.
- **Explore nicer, with more on it**: a front page of the Dota tournament scene to glance at.

They picked, for Explore (numbers from the conversation):

1. cards instead of tables
2. live series, not just live leagues
3. upcoming matches in the next 24 hours
4. recent results
5. a calendar of tournaments
6. starting soon
7. filters: tier, region, online or LAN
9. recently finished tournaments with their winners

Not wanted: 8 (tournaments your teams or tracked players play in).

## Goals

- `#tournaments` opens on Search. With the search box empty it lists the subscribed tournaments; typing searches every
  tournament, as Search does today.
- Explore opens instantly: everything on it is read from data the poller keeps, never fetched while the page loads.
- Every series on Explore with games played opens the series window (`SeriesGames.svelte`), like a bracket match.

## Non-goals

- No push or auto-refresh while Explore is open. A reload shows what the poller kept last (live games up to 5 minutes
  old).
- No streams, casters, odds, predictions or news.
- No Liquipedia images: team logos only from Steam, as today.
- No LPDB API (needs a key), no rendered Liquipedia HTML or `action=parse`: page source only, as for the tournament page.
- No new dependency. The calendar is drawn in HTML and CSS, not ECharts.

## Anti-goals

- More Liquipedia requests than its terms allow: keep the 2 s pace, the User-Agent, gzip and caching.
- Refetching a stored match or replay (project rule).
- A slow Explore: if the data is not there yet, a section says so ("filled within the next poll rounds"). It never
  waits on a fetch.

## Approaches

- **A. Built in the background; Explore only reads (picked).** The poller keeps Steam's live games, OpenDota's recent
  pro games and the Liquipedia structure of the tournaments Explore shows. Explore opens instantly. Upcoming matches can
  be up to 6 hours old, and the first fill takes a few poll rounds.
- **B. Fetched when Explore opens.** Always fresh, but the Liquipedia pace makes the first open take a minute or more.
- **C. Liquipedia for everything, results included.** Names consistent with the tournament pages, but results lag up
  to 6 hours, and the request count is far above the other two.

The user picked A: Explore is a front page to glance at. Each source does what it is best at: Steam for live, OpenDota
for fresh results, Liquipedia for schedules and winners.

## The home page (Search)

- Tabs: **Search** (first, `#tournaments`), **Explore** (`#tournaments/explore`), **Teams** (`#tournaments/teams`).
  The Subscribed tab goes. `#tournaments/subscribed` and `#tournaments/search` lead to `#tournaments`.
- **Empty search box:** "Your tournaments" is the table the Subscribed tab has today (games, teams, first and last
  game, Unsubscribe), above the "Not listed? Subscribe by league id" form. With none subscribed, a line points to
  Explore and the search box.
- **Text, or any filter changed:** the search results as today (`LeagueList`). Clearing everything shows "Your
  tournaments" again.
- Design settings (`settings.svelte.ts`): the `tournaments` group drops `list`. A hidden `list` in someone's saved
  settings is ignored.

## Explore

The order, top to bottom (my call; the user can reorder sections with the Design settings as today):

1. **Filters**: a row of chips that filters every section below. Choices are kept per viewer in the existing
   preferences, like other filters.
   - Tier: Tier 1, Tier 2, Tier 3, Lower or none (Liquipedia tier 4 and up, or no Liquipedia page). Several can be on;
     none on means all.
   - Region: the regions present in the data (Europe, CIS, China, SEA, North America, South America, MENA,
     International).
   - Online / LAN / both.
   - A live series, upcoming match or result is filtered by its tournament.
2. **Live now** (2): one card per live series, from Steam's live league games. The card shows:
   - the tournament name, linking to its page
   - both teams with logos
   - the series score and Bo{n}
   - the game clock and the kill score

   Sorted by tournament (Liquipedia tier, then prize pool), then by how long the game has run. A click opens the
   tournament page. The live game has no result yet, so the series window is not used here.
3. **Upcoming, next 24 hours** (3): matches from the kept Liquipedia structures, with both teams named, no map played,
   and a start between now and 24 hours ahead. Soonest first, at most 20. Each card shows the time, both teams (logo
   when known), Bo{n} and the tournament.
4. **Recent results** (4): the newest 20 finished series of OpenDota's recent pro games. Each card shows the
   tournament, both teams, the score and when it ended. A click opens the series window. A game opens on the match
   page if its tournament is subscribed, else on OpenDota.
5. **Starting soon** (6): tournament cards whose Liquipedia start date falls in the next 14 days, soonest first.
6. **Calendar** (5): a timeline from 14 days back to 42 days ahead, with a line for today.
   - One bar per tournament of Liquipedia tier 1 to 3 that overlaps the window.
   - A bar runs from the Liquipedia start date to the end date. Without those dates it uses the first and last game.
     A tournament with no end date yet draws its bar to today, open-ended.
   - Bars are coloured by tier. The name sits on or beside the bar, and a click opens the tournament page.
   - Rows are packed so that bars that don't overlap share a row.
7. **Biggest of the last 30 days** (today's list, as cards; 1).
8. **Recently finished** (9): tournaments of tier 1 to 3 that finished in the last 30 days, newest end first. Each card
   shows the winner's name and logo (from Liquipedia's prize pool), or "Winner not known" when the page has none.

**Tournament card** (1), used by 5, 7 and 8:
- the name, linking to the tournament page
- a status pill (Live with a pulsing dot, Active, Upcoming, Finished)
- the Liquipedia tier, the prize pool, the dates and the place (Online, or the city and country)
- the number of games
- the subscribe toggle

The cards sit in a responsive grid, one column on a phone.

Heroes are not shown on Explore. Teams show their logo when one is known for the team id (see Logos), else the name
alone.

## Data, and where it comes from

All of it is kept under `data/explore/`. `GET /api/explore` reads only kept data, the catalog table and the kept
structures, and makes no outside request. Filtering happens in the browser, because the whole answer is small (tens of
rows per section).

### Live series: Steam, every poll round

- `live_step` already asks Steam for the live league games every 5 minutes and keeps only the count per league.
- It now also writes the parsed games to `data/explore/live.json`, with the time they were read. The parsing is the
  one `league_page.live` does today, moved so both use it.
- Explore shows them only if they were read in the last 15 minutes (`LIVE_MINUTES`).
- Logos: the live answer carries each team's Steam logo id. Up to 10 new logos a round go through `steam.team_logo`,
  which keeps every answer forever.

### Recent results: OpenDota, once a poll round

- `GET https://api.opendota.com/api/proMatches` returns the last 100 pro games, with teams, league, series id, series
  type and result. It is asked at most every 10 minutes, paced with every other OpenDota call.
- Games are grouped into series by `series_id`, or by league and team pair when it is 0, as the tournament page groups
  series. The result is written to `data/explore/results.json`.
- A series counts as finished once a team has won more than half of its Bo{n} (`series_type`), or when its last game
  ended over 3 hours ago.
- The series window gets an `LpMatch`-shaped object built from the series: both teams, the maps with match ids and the
  side of the first team, and the winners. It is the same component, unchanged.

### Upcoming, winners and dates: Liquipedia, in the catalog step

- **Which tournaments get their structure kept ("Explore tournaments"):** those with a Liquipedia page that are live,
  active, starting in the next 14 days, or finished in the last 30 days, with tier 1 to 3. The cap is 15 per catalog
  round, live ones first.
- It uses `liquipedia.structure` as it is: read again after 6 hours while the tournament plays, and kept forever once
  it has finished. At 2 to 3 requests of 2 seconds each, 15 tournaments take about 90 s, and only when due.
- **Upcoming matches:** read from the kept structures when Explore is asked.
- **Winner:** `lp_structure` learns to read the prize pool. The first `{{Slot|place=1|…}}`, or `{{prize pool
  slot|place=1|…}}` on older pages, gives the opponent in first place. It is read from the event page, else from its
  `prizepool` subpage, which is then no longer left out (`NOT_STAGES`). The structure gets a `winner` field, and
  `VERSION` goes up so kept structures are read again.
- **Finding tournaments before their first game (6):** today a league is looked up on Liquipedia only once it is live,
  big or subscribed. So a tournament with no games yet never gets a start date. The catalog step now also looks up the
  50 newest leagues that OpenDota lists as premium or professional and that have no game yet. Each is asked once, as
  every lookup is (`lp_checked`), within the existing 30 lookups a round.

### Region and online

- A new catalog column `region`, filled by `liquipedia.infobox`:
  - the infobox's `region=` when it has one (to verify on real pages)
  - else the country, through a table of countries to regions in `catalog.py`
  - else none ("Unknown", which no region chip matches; it shows only when no region chip is on)
- Online comes from the infobox `type=` (`location` already starts with "Online"). LAN is any other non-empty type.
- Tournaments looked up before this change have no region. Their next due lookup fills it. For Explore tournaments
  that would take up to 7 days, so a one-time rule asks again, within the 30-a-round cap, those whose `region` is
  empty and `lp_page` is set, newest first.

### Logos

- `data/team_logos.json` maps team id to `{name, logo}`. It is written whenever a logo becomes known for a team: live
  games, tournament pages (OpenDota's league teams, Steam logos).
- Explore only reads it. Live series and results find a team by id. Upcoming matches find it by name in any case,
  because Liquipedia names teams and its structures get team ids only when a tournament page is opened. A team
  without an entry shows its name alone.

## Tests (fixtures with made-up ids and names)

- `proMatches` grouping:
  - series by id
  - series id 0 by league and team pair
  - a series finished by wins
  - a series finished by being 3 hours old
- The live games file:
  - written by `live_step` from a Steam fixture
  - older than 15 minutes, not shown
- The prize pool winner: `Slot` and `prize pool slot` forms, place 1 only, none when the page has no prize pool.
- Region:
  - from `region=`
  - from the country table
  - none
- The explore answer:
  - sections built from a kept catalog, structures and files
  - upcoming limited to 24 hours with both teams named
  - finished within 30 days, tier 1 to 3
- Explore tournaments and lookups:
  - which leagues get structures, capped at 15
  - the 50 newest pro leagues with no game are looked up
  - rows missing a region are asked again
- No test calls a live API.

## Documentation

IMPLEMENTATION.md gets an "Explore" section covering:
- each section's rule and its limits (24 h, 20, 14 days, 42 days, 30 days, tier 1 to 3, 15 structures a round, 10
  minutes for results, 15 minutes for live)
- how series are grouped
- how region is decided

The "Tournament browser" section changes for the new home page.

## Left to the builder

- The exact look of the cards, chips and calendar, in the site's existing style. A visual check at desktop and phone
  width.
- Where in the poll steps the results request goes: a step of its own or inside the catalog step. A step of its own
  shows on the Queue page like the others.
- Verifying that the Dota `{{Infobox league}}` has `region=`. If not, the country table alone decides, plus the
  infobox's other place fields.
