import { post } from './api'
import { loadConstants } from './constants.svelte'
import { remove } from './settings.svelte'

/** A league of the tournament browser (catalog.row): OpenDota's list, Steam's live games and Liquipedia */
export type CatalogRow = {
  league_id: number
  name: string
  tier: string | null // OpenDota's: premium, professional, amateur, excluded (most amateur leagues)
  games: number | null
  first_game: number | null
  last_game: number | null
  last: number | null // the last game, else Liquipedia's end date
  live_games: number
  live_seen: number | null
  lp_page: string | null // Liquipedia's page title
  lp_tier: number | null
  prize_usd: number | null
  start_date: string | null // YYYY-MM-DD
  end_date: string | null
  location: string | null
  lp_checked: number | null
  status: 'live' | 'active' | 'finished' | 'unknown'
  subscribed: boolean
}
export type Side = { team_id: number; name: string | null }
export type LeagueGame = {
  match_id: number
  start_time: number
  series_id: number | null
  series_type: number
  radiant: Side
  dire: Side
  radiant_win: boolean | null // null: not asked for (the older games of an amateur preview)
  radiant_score: number | null
  dire_score: number | null
}
export type LeagueSeries = { series_id: number | null; best_of: number; teams: [Side, Side]; score: [number, number]; start_time: number; games: number }
export type LeagueTeam = { team_id: number; name: string | null; logo: string | null; rating: number | null; seen: number; games: number; wins: number; series: number; series_wins: number }
/** From Liquipedia's page source (lp_structure.py); a team Liquipedia names that no game of ours has gets team_id 0 */
export type LpOpponent = { name: string | null; team_id: number }
export type LpMap = { team1side: string | null; winner: 0 | 1 | null; match_id: number | null }
export type LpMatch = {
  id?: string // its bracket slot, R01-M001
  opponents: [LpOpponent, LpOpponent]
  time: number | null
  match_ids: number[]
  maps: LpMap[]
  score: [number, number]
  winner: 0 | 1 | null
  feeders?: string[] // the slots whose teams it gets
  best_of: number | null
}
/** One game of a series: result, length, and picks and bans of [Radiant, Dire]; picks null when no one has the draft */
export type Draft = {
  match_id: number; stored: boolean; duration: number | null; radiant_win: boolean | null
  radiant_team_id: number | null; dire_team_id: number | null; picks: [number[], number[]] | null; bans: [number[], number[]] | null
}
export type LpBracket = { title: string; sections: { name: 'upper' | 'lower'; rounds: { name: string; matches: LpMatch[] }[] }[] }
export type Record_ = { name: string | null; team_id: number; series_wins: number; series_losses: number; map_wins: number; map_losses: number }
export type Liquipedia = {
  page: string
  brackets: LpBracket[]
  groups: { title: string; rows: Record_[] }[]
  upcoming: LpMatch[]
  rosters: { name: string; team_id: number; players: { handle: string; role: string | null; sub: boolean }[] }[]
}
export type LiveGame = { match_id: number; radiant: Side; dire: Side; series: [number, number]; best_of: number; duration: number | null; score: [number | null, number | null] }
export type HeroStat = { hero_id: number; picks: number; wins: number; bans: number; contested: number }
export type PlayerStat = {
  account_id: number; name: string | null; avatar: string | null; team_id: number; games: number; wins: number
  kills: number; deaths: number; assists: number; kda: number; gpm: number; xpm: number; last_hits: number; hero_damage: number
  heroes: number[]
}
export type Played = { account_id: number; name: string | null; avatar: string | null; games: number }
export type HeadToHead = {
  teams: [Side, Side]
  games: number
  wins: [number, number]
  series: { league_id: number; league_name: string | null; start_time: number; score: [number, number] }[]
}
export type LeaguePage = {
  league: CatalogRow
  source: 'stored' | 'opendota' | 'steam' | 'none'
  subscribed: boolean
  teams: LeagueTeam[]
  series: LeagueSeries[]
  games: LeagueGame[]
  standings: Record_[]
  liquipedia: Liquipedia | null
  live: LiveGame[]
  heroes?: HeroStat[] // the stats of a subscribed league, from its stored games
  players?: PlayerStat[]
  rosters?: Record<string, Played[]> // team id → the players seen playing for it
}

/** Follow a league or stop: the poller then fetches its games, or no more of them. */
export async function subscribe(row: { league_id: number; subscribed: boolean }, on: boolean) {
  if (on) await post('leagues', { league_id: String(row.league_id) }) // as text: no JavaScript rounding of the id
  else await remove(`leagues/${row.league_id}`)
  row.subscribed = on
  loadConstants() // the header's Tournament filter lists the subscribed leagues
}

export const TIERS: Record<string, string> = { premium: 'Premium', professional: 'Pro', amateur: 'Amateur', excluded: 'Amateur' }
export const tierName = (tier: string | null) => TIERS[tier ?? ''] ?? 'Amateur'
export const STATUS = { live: 'Live', active: 'Active', finished: 'Finished', unknown: 'Unknown' }
export const money = (usd: number | null) => (usd === null ? '' : `$${usd.toLocaleString('en-US')}`)
export const day = (seconds: number | null) =>
  seconds === null ? '' : new Date(seconds * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
const fromDate = (date: string | null) => (date ? Date.parse(`${date}T12:00:00Z`) / 1000 : null)
/** When it ran: its first and last game, else Liquipedia's dates */
export function dates(r: CatalogRow) {
  const [from, to] = r.first_game !== null ? [r.first_game, r.last] : [fromDate(r.start_date), fromDate(r.end_date)]
  return from === null ? (to === null ? '' : `until ${day(to)}`) : to === null || day(from) === day(to) ? day(from) : `${day(from)} – ${day(to)}`
}
export const liquipedia = (page: string) => `https://liquipedia.net/dota2/${encodeURI(page.replaceAll(' ', '_'))}`
/** 14 Nov, 18:00 in the viewer's time */
export const moment = (seconds: number) =>
  new Date(seconds * 1000).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

/** GET /api/explore (explore.py): every section, and the leagues they name with region and whether online */
export type ExploreLeague = CatalogRow & { region: string | null; online: boolean }
export type ExploreTeam = LpOpponent & { logo: string | null }
export type LiveSeries = {
  league_id: number; match_id: number; radiant: ExploreTeam; dire: ExploreTeam; series: [number, number]; best_of: number
  duration: number | null; score: [number | null, number | null]
}
export type ExploreMatch = Omit<LpMatch, 'opponents'> & { opponents: [ExploreTeam, ExploreTeam]; league_id: number; league_name?: string }
export type ExploreAnswer = {
  leagues: Record<string, ExploreLeague>
  live: LiveSeries[]
  upcoming: ExploreMatch[]
  results: ExploreMatch[]
  soon: number[]
  calendar: { league_id: number; start: number; end: number; open: boolean }[]
  big: number[]
  finished: { league_id: number; winner: { name: string; logo: string | null } | null }[]
}
/** GET /api/home (explore.home): Explore of your tournaments; mine are their ids, live first, then by last game */
export type HomeAnswer = Pick<ExploreAnswer, 'leagues' | 'live' | 'upcoming' | 'results'> & { mine: number[] }
/** Explore's tier groups and their colour, the same on cards and calendar bars */
export const TIER_GROUPS = { '1': 'Tier 1', '2': 'Tier 2', '3': 'Tier 3', lower: 'Lower' } as const
export type TierGroup = keyof typeof TIER_GROUPS
export const tierGroup = (lpTier: number | null): TierGroup => (lpTier && lpTier <= 3 ? (String(lpTier) as TierGroup) : 'lower')
export const TIER_COLOR: Record<TierGroup, string> = { '1': 'var(--series-4)', '2': 'var(--series-1)', '3': 'var(--series-3)', lower: 'var(--axis)' }
