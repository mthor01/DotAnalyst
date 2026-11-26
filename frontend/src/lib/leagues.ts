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
export type LeaguePage = {
  league: CatalogRow
  source: 'stored' | 'opendota' | 'steam' | 'none'
  subscribed: boolean
  teams: LeagueTeam[]
  series: LeagueSeries[]
  games: LeagueGame[]
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
