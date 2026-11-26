# Tournament browser — design

Approved in conversation on 2026-11-26 ("yes do it").

## Why

Today a tournament is followed by typing its league id into a form. The user wants to find tournaments without
knowing ids: see what big tournaments run now, search every league by name with filters and sorting, open a page
with everything known about a tournament, and subscribe or unsubscribe from there. Amateur leagues matter as much
as pro ones: one of the two tournaments the user follows is an amateur league.

## Goals

1. **Explore**: the current big tournaments, and the leagues playing right now, amateur ones included.
2. **Search**: every league by name, filtered by tier and status, sorted by name, last game, games, prize pool or
   newest.
3. **Tournament page** for any league, subscribed or not: what it is, when, its teams, its series results, its
   latest games; subscribe and unsubscribe on it.

## Non-goals

- Brackets and group tables from Liquipedia: their markup is fragile to parse. The page links to Liquipedia instead.
- Stats (replays, wards, drafts) for leagues not subscribed: subscribing is what fetches those, as today.
- Push notifications for new tournaments.

## Anti-goals

- Fetching a league's whole history just because it showed in a list. Only opening its page, or subscribing,
  costs requests for it.
- A preview league's games joining the stats, the team pages or the replay downloads. Preview data never goes into
  `league_matches`.

## Sources (decided: OpenDota and Liquipedia, amateur leagues always included)

| What | Source | Cost |
|---|---|---|
| Every league: id, name, tier | OpenDota `GET /api/leagues` (about 10,400 leagues, 1 MB) | 1 request a day |
| Games, first and last game of pro leagues of the last year | OpenDota explorer, one SQL query over its pro matches | 1 request a day |
| Leagues playing right now, amateur ones too | Steam `GetLiveLeagueGames` | 1 request every 5 minutes |
| Prize pool, Liquipedia tier, dates, location, page link | Liquipedia MediaWiki API: one `generator=search` request for `insource:"leagueid=<id>"` with the page's wikitext | 1 request per league, at most one every 2 seconds |
| A pro league's games and teams for its page | OpenDota `/api/leagues/<id>/matches` and `/teams` | 2 requests when the page is opened |
| An amateur league's games for its page | Steam `GetMatchHistory` with `league_id` (up to 5 pages) and the details of its newest 20 games | up to 25 Steam requests, once |

Measured on 2026-11-26: OpenDota has no games for the user's amateur league, Steam has 178; Steam's live list had
22 games in 15 leagues, all tier "excluded" (OpenDota's tier for amateur leagues); Liquipedia's search found
DreamLeague Division 2/5 from its league id with tier 3 and $50,000.

Liquipedia requests send `User-Agent: DotAnalyst/<version> (+https://github.com/mthor01/DotAnalyst)` (approved by the
user) and accept gzip, as Liquipedia's terms ask. The tournament page credits Liquipedia (CC BY-SA 3.0) where it
shows its data.

## Data

One new table, `league_catalog`, a row per league in OpenDota's list plus any league seen live or subscribed that the
list lacks:

- `league_id`, `name`, `tier` (OpenDota's: premium, professional, amateur, excluded, or none)
- `games`, `first_game`, `last_game`: from the explorer for pro leagues, from a page preview or the stored games
  otherwise; null when unknown
- `live_games`, `live_seen`: the live games in the last look that had any, and when
- Liquipedia: `lp_page` (title, null when none found), `lp_tier` (1–5), `prize_usd`, `start_date`, `end_date`,
  `location`, `lp_checked` (when asked; null never asked)

The daily refresh merges into it and never deletes a row. A page preview (games, teams, series) is kept as
`data/leagues/<id>.json`; it is fetched again only when the league played in the last 30 days and the file is older
than 6 hours. A finished league's preview is never fetched again.

## Behaviour

**Status** of a league: *live* when seen in the live list in the last 15 minutes; *active* when its last game is
within 30 days; *finished* when older; *unknown* without dates. Liquipedia's end date counts as a last game when there
is no game date.

**Explore** shows:
1. *Live now*: leagues with status live, most live games first.
2. *Biggest of the last 30 days*: active leagues ranked by Liquipedia tier (1 first; none last), then prize pool, then
   games. At most 20.

**Search** runs on the server over `league_catalog`: name contains the text (case-insensitive), tier filter (premium,
professional, amateur: amateur means tier amateur, excluded or none), status filter, sort by name, last game, games,
prize pool or newest (highest id). 50 rows a page with "Show more". Every row has Subscribe / Subscribed.

**Tournament page** (`#league/<id>`):
- Header: name, OpenDota tier, Liquipedia tier, prize pool, dates, location, game count, status, Subscribe button,
  link to Liquipedia and its credit.
- Teams: logo where known, series and game record, OpenDota rating for pro leagues.
- Series: grouped by `series_id`; each shows the two teams, the score and Bo-type (0 → Bo1, 1 → Bo3, 2 → Bo5), newest
  first.
- Latest games: date, teams, score, winner; a subscribed league's games link to the match page and its teams to the
  team pages.
- A subscribed league shows the stored games (`league_matches`), others the preview.

**Subscribing** adds the `League` row with the catalog's name (no OpenDota call), as `POST /api/leagues` does today;
the poller then fetches its games. **Unsubscribing** is today's `DELETE /api/leagues/<id>`.

**The poller** gets two steps: *live* (Steam live list, every 5 minutes) and *catalog* (the daily OpenDota list and
explorer query, then Liquipedia lookups for the leagues in Explore and the subscribed ones that were never asked, or
asked more than 7 days ago while active). Both obey Pause. A Liquipedia lookup for an opened page that was never asked
happens when the page is opened.

## Site

The Tournaments page's tabs become **Explore**, **Search**, **Subscribed** (today's list, id kept as
`tournaments.list` so saved Design settings still apply) and **Teams**. Explore opens first. The league id form moves
under Search as "Add by league id" for leagues missing from every list. The Design page gets `tournaments.explore`,
`tournaments.search` and a `league` group (header, teams, series, games).

## Left to the builder

Table layout, names of functions and routes, how the explorer SQL is written, which infobox fields map to dates and
location, test fixture contents (made-up ids and names).
