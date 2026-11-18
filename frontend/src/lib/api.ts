export type Account = {
  account_id: number
  label: string | null
  history_exposed: boolean | null
  avatar: string | null // Steam profile picture; "" when there is none, null until the poller asked
}

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
  radiant: boolean
  /** lane to obs_lifetime come from the replay: null without one. `lane_nw_diff` is also null outside the three
   *  lanes, `obs_lifetime` (mean seconds an observer stood) when none of the player's was removed before the end. */
  lane: 'top' | 'mid' | 'bot' | 'jungle' | null
  lane_nw_diff: number | null
  obs_bought: number | null
  sen_bought: number | null
  wards_destroyed: number | null
  obs_lifetime: number | null
  /** the laning numbers at 10:00 (kills and deaths before it), see dotanalyst/metrics.py; null without a replay, in
   *  a match that ended before 10:00, and (lane_cs_diff and the two lane damages) outside the three lanes */
  lane_cs_diff: number | null
  last_hits_at_10: number | null
  denies_at_10: number | null
  net_worth_at_10: number | null
  xp_at_10: number | null
  damage_at_10: number | null
  damage_taken_at_10: number | null
  lane_damage_at_10: number | null
  enemy_lane_damage_at_10: number | null
  kills_by_10: number | null
  deaths_by_10: number | null
  /** whole-match totals from the replay (lotuses collected, camps pulled, trips through a twin gate), null without one */
  lotuses: number | null
  camps_pulled: number | null
  twin_gates: number | null
  /** the enemy heroes in the player's lane, empty without a replay or outside the three lanes */
  lane_enemies: number[]
  party: boolean // queued with someone, see Solo or party in IMPLEMENTATION.md
  with_tracked: boolean
  position: 1 | 2 | 3 | 4 | 5 // from the lane and the farm, see IMPLEMENTATION.md
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
  /** Picks and bans in draft order, from Steam's answer; empty in modes without a draft */
  draft: { hero_id: number; pick: boolean; radiant: boolean }[]
  player_minute: { player_slot: number; minute: number; gold: number; xp: number; net_worth: number; last_hits: number; denies: number; hero_damage: number; healing: number; camps_stacked: number; camps_pulled: number; lotuses: number }[]
  purchases: { player_slot: number; time: number; item: string; built_at: number | null }[]
  /** Skill points in the order they were spent; a talent's `ability` starts with special_bonus_. */
  ability_upgrades: { player_slot: number; time: number; ability: string; level: number; hero_level: number | null }[]
  deaths: { player_slot: number; time: number; x: number | null; y: number | null; killer_slot: number | null; in_teamfight: boolean }[]
  teamfights: { n: number; start: number; end: number; deaths: number }[]
  teamfight_players: { n: number; player_slot: number; took_part: boolean; damage: number; healing: number; deaths: number; net_worth_gain: number; xp_gain: number }[]
  wards: { player_slot: number; type: 'obs' | 'sen'; x: number; y: number; placed: number; removed: number | null; killed: boolean; killed_by: number | null }[]
  /** The towers, barracks and Ancients that fell, in that order; one that is not listed stood to the end. */
  buildings: { name: string; time: number }[]
  lanes: { player_slot: number; lane: string | null }[]
}

export type TeamRow = { team_id: number; name: string | null; games: number; wins: number; last_played: number }
/** Something the poller did to one match's replay, or to none (`match_id` null). Times are unix seconds. */
export type QueueEvent = { at: number; match_id: number | null; message: string }
/** What the poller has to do: every match whose replay it still wants, in the order it takes them. */
export type QueueStatus = {
  doing: string
  since: number
  busy: boolean
  now: number
  last_poll: { at: number; seconds: number; new?: number; parsed?: number; error?: string } | null
  next_poll: number | null
  parser: boolean
  alt: boolean
  salts_from_steam: number
  per_poll: number
  retry_seconds: number
  max_age_days: number
  states: Record<string, number>
  without_stats: number
  folder: { ready: number; downloading: number }
  queue: { match_id: number; start_time: number; league: boolean; state: string; tried_at: number | null; next_try: number; last: QueueEvent | null }[]
  events: QueueEvent[]
}
/** A ward as a heatmap needs it: its kind, its place in map cells, and the side its owner played. */
/** time: game second placed; league: on team pages, whether the game is one of the team's tournament games */
export type WardSpot = { match_id: number; type: 'obs' | 'sen'; x: number; y: number; radiant: boolean; time: number; win: boolean; league?: boolean }
/** One hero in a team's league drafts. `open` counts the games in which neither side banned it and the other side
 *  did not pick it (`picked_against`). */
export type TeamHero = { hero_id: number; banned_against: number; banned: number; picked_against: number; open: number; picked: number; wins: number }
/** A league player's games on one hero; the numbers after `wins` are averages per game. */
export type TeamPlayerHero = { hero_id: number; games: number; wins: number; kills: number; deaths: number; assists: number; last_hits: number; gold_per_min: number; xp_per_min: number }
export type TeamDetail = {
  team_id: number
  name: string | null
  /** URL of the team's logo, null when Steam has none */
  logo: string | null
  /** Newest first. `picks` are in player slot order; `replay` says whether the game's replay is parsed. */
  games: { match_id: number; start_time: number; league: string; radiant: boolean; win: boolean; opponent_id: number; opponent: string | null; picks: number[]; picks_against: number[]; bans: number[]; bans_against: number[]; replay: boolean
    /** From the parsed replay, null without one: the game's first Tormentor and whether they drew first blood */
    tormentor: { time: number; taken: boolean; enemies_dead: number; lead: number } | null
    first_blood: boolean | null
  }[]
  heroes: TeamHero[]
  /** `wards` are those of the `replays` games of the player whose replay is parsed. `outside` are the player's last
   *  games outside the league, newest first, whatever the filters; `outside_listed` is false until they were asked for.
   *  `usual_waiting`: usual games of the last 30 days whose replay the poller still means to get, null until Refresh
   *  on the team page asked for them. */
  players: {
    account_id: number; name: string | null; games: number; replays: number; usual_replays: number; heroes: TeamPlayerHero[]; wards: WardSpot[]; parsed: { radiant: boolean; league: boolean; win: boolean }[]
    outside_listed: boolean
    usual_waiting: number | null
    outside: { match_id: number; hero_id: number; win: boolean; role: 'safe' | 'mid' | 'off' | 'jungle' | 'none'; kills: number | null; deaths: number | null; assists: number | null }[]
  }[]
  /** Each parsed game's first Tormentor, taken by them or by the enemy: how many, and the mean time, enemies dead and
   *  net worth lead of the side that took it (null with none to average) */
  tormentors: { games: number; them: TeamTormentors; enemy: TeamTormentors }
  /** Their safe, mid and off lane at 10:00 of the parsed games: games, games ahead in net worth, mean leads */
  lanes: Record<'safe' | 'mid' | 'off', { games: number; ahead: number; net_worth: number | null; xp: number | null }>
  /** `own` is the wisdom rune in their half of the map. Contested: at least one of their heroes came to it. Kills and
   *  deaths: heroes of the enemy and of theirs that died at the rune, per game (null without games). */
  wisdom: { own: TeamWisdom; enemy: TeamWisdom }
  /** draft[k][p]: how often their (k+1)-th pick played position p+1, in their parsed Captains Mode games */
  draft: number[][]
}
export type TeamTormentors = { count: number; time: number | null; enemies_dead: number | null; lead: number | null }
export type TeamWisdom = { spawns: number; contested: number; heroes: number | null; taken: number; lead: number | null; kills: number | null; deaths: number | null }

export type MetricPoint ={ match_id: number; start_time: number; value: number }
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
  { name: 'obs_bought', label: 'Observers bought', show: count },
  { name: 'sen_bought', label: 'Sentries bought', show: count },
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
  /** Ability name as in replays -> the name the game shows. */
  abilities: Record<string, string>
  /** The tracked leagues, one per season: league id -> "Season 8". */
  leagues: Record<number, string>
}

export async function get<T>(path: string, query = ''): Promise<T> {
  const response = await fetch(`/api/${path}${query ? `?${query}` : ''}`)
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  return response.json()
}

/** A request that makes the server do something. The server's own words are the error message. */
export async function post<T>(path: string): Promise<T> {
  const response = await fetch(`/api/${path}`, { method: 'POST' })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `${path}: HTTP ${response.status}`)
  return response.json()
}

export const LOBBY_TYPES: Record<number, string> = { 0: 'Normal', 1: 'Practice', 7: 'Ranked' } // a league game is a practice lobby
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
