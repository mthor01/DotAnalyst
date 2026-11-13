export type Account = { account_id: number; label: string | null; history_exposed: boolean | null }

export type MatchRow = {
  match_id: number
  start_time: number
  duration: number
  game_mode: number
  lobby_type: number
  replay_state: string
  win: number
  hero_id: number
  kills: number
  deaths: number
  assists: number
  last_hits: number
  denies: number
  gold_per_min: number
  xp_per_min: number
  net_worth: number
  items: number[]
}

export type HeroRow = {
  hero_id: number
  games: number
  wins: number
  kills: number
  deaths: number
  assists: number
  gold_per_min: number
  xp_per_min: number
}

export type TeammateRow = { account_id: number; label: string | null; games: number; wins: number }

export type MatchupRow = {
  hero_id: number
  with_games: number
  with_wins: number
  against_games: number
  against_wins: number
}

export type MatchPlayer = {
  player_slot: number
  account_id: number | null
  label: string | null
  hero_id: number
  kills: number
  deaths: number
  assists: number
  last_hits: number
  denies: number
  gold_per_min: number
  xp_per_min: number
  net_worth: number
  level: number
  hero_damage: number | null
  items: number[]
}

/** One match. The lists after `players` come from the replay and are empty when there is none. */
export type MatchDetail = {
  match_id: number
  start_time: number
  duration: number
  radiant_win: boolean
  game_mode: number
  lobby_type: number
  replay_state: string
  players: MatchPlayer[]
  player_minute: { player_slot: number; minute: number; gold: number; xp: number; net_worth: number; last_hits: number; denies: number; camps_stacked: number; lotuses: number }[]
  purchases: { player_slot: number; time: number; item: string }[]
  deaths: { player_slot: number; time: number; x: number | null; y: number | null; killer_slot: number | null; in_teamfight: boolean }[]
  teamfights: { n: number; start: number; end: number; deaths: number }[]
  teamfight_players: { n: number; player_slot: number; took_part: boolean; damage: number; deaths: number }[]
  wards: { player_slot: number; type: 'obs' | 'sen'; x: number; y: number; placed: number; removed: number | null; killed: boolean; killed_by: number | null }[]
  lanes: { player_slot: number; lane: string | null }[]
}

export type MetricPoint = { match_id: number; start_time: number; value: number }
export type MetricAverage = { name: string; average: number; matches: number }

const signed = (digits: number) => (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(digits)}`
const share = (v: number) => `${Math.round(100 * v)}%`
const count = (v: number) => v.toFixed(2)
/** The metrics of dotanalyst/metrics.py, in display order, each with how to print a value or an average. */
export const METRICS: { name: string; label: string; show: (v: number) => string }[] = [
  { name: 'lane_cs_diff', label: 'Lane last hits at 10:00 vs enemy lane', show: signed(1) },
  { name: 'lane_nw_diff', label: 'Lane net worth at 10:00 vs enemy lane', show: signed(0) },
  { name: 'kill_participation', label: 'Kill participation', show: share },
  { name: 'fight_participation', label: 'Teamfights taken part in', show: share },
  { name: 'deaths_outside_fights', label: 'Deaths outside teamfights', show: count },
  { name: 'obs_placed', label: 'Observers placed', show: count },
  { name: 'sen_placed', label: 'Sentries placed', show: count },
  { name: 'wards_destroyed', label: 'Enemy wards destroyed', show: count },
  { name: 'obs_lifetime', label: 'Observer lifetime', show: (v) => `${Math.round(v)} s` },
]

/** The shared filters, but for another account. */
export function queryFor(query: string, accountId: number, more: Record<string, string> = {}): string {
  return new URLSearchParams({ ...Object.fromEntries(new URLSearchParams(query)), ...more, account_id: String(accountId) }).toString()
}

export type Constants = {
  heroes: Record<number, { name: string; localized_name: string }>
  items: Record<number, string>
}

export async function get<T>(path: string, query = ''): Promise<T> {
  const response = await fetch(`/api/${path}${query ? `?${query}` : ''}`)
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  return response.json()
}

export const LOBBY_TYPES: Record<number, string> = { 0: 'Normal', 7: 'Ranked' }
export const GAME_MODES: Record<number, string> = {
  1: 'All Pick',
  2: 'Captains Mode',
  3: 'Random Draft',
  4: 'Single Draft',
  5: 'All Random',
  18: 'Ability Draft',
  22: 'All Pick',
  23: 'Turbo',
}

/** Game clock: 754 -> 12:34, -89 -> -1:29 (before the horn). */
export function clock(seconds: number): string {
  const s = Math.abs(seconds)
  return `${seconds < 0 ? '-' : ''}${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export const percent = (part: number, whole: number) => (whole ? Math.round((100 * part) / whole) : 0)

/** Sort rows by a number each row yields; ties keep their order. */
export function sortedBy<T>(rows: T[], value: (row: T) => number, descending: boolean): T[] {
  return [...rows].sort((a, b) => (descending ? value(b) - value(a) : value(a) - value(b)))
}
