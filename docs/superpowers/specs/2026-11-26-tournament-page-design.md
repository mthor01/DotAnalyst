# Tournament page: brackets, standings, teams and stats

## Intent

The tournament page (`#league/<id>`) lists a league's facts, teams, series and games as plain tables today. The user
wants it to read like a real event page: team logos, results tables and a bracket tree. They picked what goes on it:

1. bracket tree (Liquipedia leagues)
2. group / standings tables: Liquipedia's groups when it has them, else standings worked out from series results
3. upcoming and live series
6. team rosters
7. most picked and banned heroes
8. top players
9. head-to-head between two teams

Not wanted: prize split by placement, streams / VODs.

Order of work (my call, from the conversation): the stats sections from stored games first (they serve the user's
amateur leagues today), then the Liquipedia structure.

## Goals

- Pro leagues on Liquipedia get their real bracket tree, groups, upcoming matches and rosters, drawn in the site's
  own style with team logos, each played match linking to its games.
- Every league with games gets a standings table, Liquipedia or not.
- Subscribed leagues get hero, player and head-to-head stats from their stored games.

## Non-goals

- No bracket for a league Liquipedia does not cover: series data cannot tell upper from lower bracket, so those get
  standings only.
- No stats (7, 8, 9) for unsubscribed leagues: a preview has no player data. The sections say "Subscribe to see …".
- No prize split, streams, casters, VODs, Liquipedia's hero drafts (our games have the drafts).
- No Liquipedia images (team logos there are not CC BY-SA).
- No LPDB API (needs a key), no `action=parse` (30 s rate limit).

## Anti-goals

- Fetching more from Liquipedia than its terms allow: keep the 2 s pace, the User-Agent, gzip, and caching.
- Refetching stored matches or replays (project rule).
- Committing anything that identifies a real player: all new fixtures use invented team names, handles and match ids.

## Approaches

1. **Liquipedia page source, drawn by us (chosen).** Read the wikitext of the event page and its stage subpages, plus
   the bracket layout page from Liquipedia's commons wiki, parse the `Bracket`, `Matchlist`, `GroupStandings` and
   `TeamParticipants` templates, draw everything in Svelte. Our logos, our links. Cost: a template parser and subpage
   handling.
2. Liquipedia's rendered HTML (`action=parse`): one request per 30 s, their markup and images, breaks with their
   markup. Rejected.
3. Infer the tree from our series: cannot place upper/lower bracket. Rejected as a tree; it is the standings fallback.

## Data sources and how each section is built

### Liquipedia structure (sections 1, 2, 3 upcoming, 6)

Fetched for a league whose catalog row has `lp_page`.

- **Pages.** `list=allpages&apprefix=<lp_page>/` gives the subpages. Keep direct children only (no further `/`), drop
  `Statistics` and `prizepool`. Fetch the event page and those children in **one** request (`titles=A|B|…`,
  `prop=revisions`, at most 50). Drop a child whose wikitext has its own `{{Infobox league` with a different
  `leagueid`: that is a qualifier, another league (TI's region pages).
- **Layouts.** Each `{{Bracket|Bracket/<layout>|…}}` names a layout. Its page is
  `Template:Bracket/<layout>` on `https://liquipedia.net/commons/api.php`; it lists
  `{{TemplateMatch|matchid=R03-M001|toupper=R01-M001|tolower=R01-M002|header=!u3!x|root=true|bracketreset=RxMBR}}`.
  Layouts never change: cached forever in `data/leagues/brackets.json` (layout → parsed list).
- **Matches.** In a `Bracket`, `|R1M1={{Match …}}` is layout match `R01-M001`. In a `Matchlist`, `|M1=`… in page
  order. Per match: the two `{{TeamOpponent|<name>}}`, `date=` (e.g. `November 13, 2026 - 11:00 {{Abbr/CET}}`),
  `matchid1..n` (Dota match ids), each `map<k>={{Map …|team1side=radiant|winner=1}}` (`finished=skip` maps are not
  played). Score = maps won per opponent; a `|winner=` on the Match wins over counting.
- **Round names.** A page's own `R1M1header=` wins; else decode the layout's header code (`!u1!` Grand Final, `!u2!`
  Upper Bracket Final, `!u3!` Upper Bracket Semifinals, `!u4!` Upper Bracket Quarterfinals, `!l2!` Lower Bracket Final,
  `!l3!` Lower Bracket Semifinal, `!l4!` Lower Bracket Quarterfinals, `!lx!N` Lower Bracket Round N …); unknown → "Round
  N".
- **Sections of a bracket.** Layout matches after a header starting `!l` belong to the lower bracket until the next
  `!u` header; others are upper. A single-elimination layout has only upper. The bracket reset (`RxMBR`) is drawn after
  the grand final only when it was played.
- **Groups.** Each `{{GroupStandings …}}` gives a title (the `===Group A===` heading above it, else its `title=`) and its
  members. Standings are computed from every `Matchlist`/`Bracket` match on the same page whose two opponents are both
  members: series won–lost, then maps won–lost, then map difference. Manual tiebreakers are ignored (known limit).
- **Upcoming.** A match with no map played yet, both opponents named (not `TBD`/empty), and a date no earlier than
  12 h ago (a stale unplayed match is not upcoming). Soonest first, at most 10.
- **Rosters.** `{{TeamParticipants}}` → per team its `{{Person|role=…|<handle>|status=sub}}` entries (handle, role, sub).
- **Team identity.** A Liquipedia name maps to a Dota team id through the page's games: for a played map with
  `matchid<k>` among our games (stored or preview), `team1side` says which side opponent 1 was. Failing that, a
  case-insensitive name match against the league's teams. Unmapped names show without a logo or link.
- **Timezones.** A small table of the abbreviations Liquipedia uses (CET, CEST, EET, EEST, UTC, GMT, SGT, CST, PST, PDT,
  EST, EDT, …); unknown → UTC, shown as the day only.
- **Caching.** The parsed structure is kept in `data/leagues/<id>.lp.json` with the time it was fetched. Refreshed with
  the preview's rule: older than PREVIEW_HOURS (6 h) and the league not finished; a finished league's is never fetched
  again. A failed request keeps the old file. Liquipedia's `pace()` (2 s) before every request.

### Live series (section 3, live)

When the catalog says the league is live (`status == "live"`) and there is a Steam key, the page asks Steam
`GetLiveLeagueGames?league_id=<id>` on load (not cached in the preview file): per game the two teams, series score,
game time, kill score. Shown above upcoming.

### Standings without Liquipedia (section 2 fallback)

When Liquipedia has no groups for the league, one table from the page's series: series won–lost, maps won–lost, map
difference, sorted that way. Only series with a known result count (as the team records do today).

### Teams and logos (section 6)

The Teams table becomes team rows with logo, records and an expandable roster.

- **Logos:** OpenDota's `logo_url` for pro previews (today); for stored games, the Steam UGC logo
  (`radiant_logo`/`dire_logo` in `raw_json`) through `steam.team_logo`, which caches every answer in `data/logos.json`.
- **Roster:** Liquipedia's when it has one; else, for a subscribed league, the players seen playing for the team in its
  stored games: name and picture from `PlayerName`, games played.

### Stats from stored games (sections 7, 8, 9; subscribed leagues only)

From `LeagueMatch.raw_json` (`players`, `picks_bans`), computed per request.

- **Heroes:** per hero picks, wins, win rate, bans, contested % ((picks + bans) / games). Hero by `heroIcon`, name in
  `alt`/`title`. Sorted by contested, client-side sortable.
- **Players:** per account (anonymous left out) team (logo), games, wins, average K / D / A, KDA ratio, GPM, XPM, last
  hits, hero damage, top three heroes (icons). Sortable; default by games.
- **Head-to-head:** two team pickers holding the league's teams; the record between them across **all stored league
  games** (any subscribed league): series won, games won, and the list of their series with tournament, day and score.
  A new endpoint `GET /api/teams/{a}/vs/{b}`.

## Page layout

Tabs inside the league page, `#league/<id>/<tab>` (the site's `.choice tabs` pattern; my call, the page would be very
long otherwise):

```
[Tournament name]                          [Subscribe]
Status · When · Games · Tier · Prize · Where
Overview | Teams | Stats | Games
Overview: Live now → Upcoming → Bracket (horizontal scroll, upper then lower,
          lines from feeder to match, logos, score, played match → its games)
          → Groups / Standings
Teams:    team rows (logo, series, games, rating) → roster on expand
Stats:    Heroes · Players · Head-to-head     ("Subscribe to see …" when not)
Games:    Series · Latest games   (today's tables)
```

Each section gets a `data-block` id (`league.live`, `league.upcoming`, `league.bracket`, `league.groups`,
`league.teams`, `league.heroes`, `league.players`, `league.h2h`, `league.series`, `league.games`) and an entry in the
Design settings tree. A section with no data is left out, not shown empty.

## API

`GET /api/leagues/{id}/page` grows: `liquipedia: {brackets: [{title, rounds…}], groups: [...], upcoming: [...],
rosters: {...}} | null`, `live: [...]`, `standings: [...]`, and for subscribed leagues `heroes`, `players`. The exact
shapes are the builder's. `GET /api/teams/{a}/vs/{b}` is new.

## Documentation

IMPLEMENTATION.md gets sections for: the Liquipedia structure (pages, layouts, matches, groups, upcoming, team identity,
caching), standings, live series, hero stats, player stats, head-to-head; the Storage list gains `brackets.json` and
`<id>.lp.json`.

## Tests

pytest, fixtures only, no live calls; all names and ids invented:

- a small event page wikitext with a `Bracket`, a `Matchlist`, two `GroupStandings`, a `TeamParticipants`; a commons
  layout; an allpages answer with a qualifier child and a `Statistics` child;
- parser: layout linkage and upper/lower sections, round names (page header beats code, unknown code), series score
  with a skipped map and an explicit winner, upcoming detection, group standings, rosters, the qualifier child
  dropped, team identity by match id and by name, timezone parse;
- caching: layout fetched once ever; structure refetched after 6 h only while not finished; a failed request keeps
  the old file;
- standings fallback from series; heroes, players and head-to-head from stored `LeagueMatch` rows.

## Left to the builder

Exact JSON shapes, the bracket drawing (CSS grid or SVG for the lines), the header-code table beyond the codes above,
the timezone table, how a long round name wraps.

## Known limits

- Liquipedia can match the wrong page for a league (seen with FACEIT 17599); its bracket is then wrong too.
- Group tiebreakers set by hand on Liquipedia are ignored.
- A league whose stages sit deeper than one subpage level, or in pages that are not its subpages, shows only what the
  direct subpages have.
