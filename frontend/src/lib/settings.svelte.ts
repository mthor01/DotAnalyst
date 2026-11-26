import { get, post } from './api'

/** What GET /api/settings answers (settings.py): the values the settings page shows and changes */
export type Settings = {
  auto_update: boolean
  paused: boolean
  download_limit: number // KB/s over all downloads together, 0: no cap
  check_seconds: number
  max_age_days: number
  main_account: string // '' for none
  alt_user: string
  alt_password: boolean // only whether there is one
  hidden: string // the Design page's hidden parts, ids joined by commas
  steam_key: boolean
  replay_dir: string | null // null: Steam's own folder, '': none
  start_with_windows: boolean | null // null: run from source, nothing to start
  data_folder: string
}

export const prefs = $state<{ s: Settings | null }>({ s: null })

export async function loadSettings() {
  prefs.s = await get<Settings>('settings')
}

/** Change some settings; the server checks them all and answers with every value. Throws with its reason. */
export async function saveSettings(changes: Partial<Record<keyof Settings, unknown>>) {
  prefs.s = await post<Settings>('settings', changes)
}

/** A request that stops tracking something; the server's own words are the error message. */
export async function remove(path: string) {
  const response = await fetch(`/api/${path}`, { method: 'DELETE' })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `${path}: HTTP ${response.status}`)
}

export const hiddenIds = () => (prefs.s?.hidden ? prefs.s.hidden.split(',') : [])
/** Whether a part is hidden, itself or by its page or tab: ids nest with dots, profile.laning.versus */
export const isHidden = (id: string) => hiddenIds().some((h) => id === h || id.startsWith(`${h}.`))

/** The parts the Design page can hide, as the site shows them. A part marks its elements with data-block="<id>";
 *  `group` is only a heading there (the match, team and tournament pages are opened from links, not hidden as a whole). */
export type Part = { id: string; label: string; parts?: Part[]; group?: true }
const part = (id: string, label: string, parts?: Part[]): Part => ({ id, label, ...(parts && { parts }) })
const within = (prefix: string, list: [string, string][]) => list.map(([id, label]) => part(`${prefix}.${id}`, label))
export const DESIGN: Part[] = [
  part('profile', 'Profile', [
    part('profile.overview', 'Overview', within('profile.overview', [
      ['numbers', 'Key numbers'], ['roles', 'Role wheel'], ['heroes', 'Most played heroes'], ['activity', 'Activity'],
      ['form', 'Form'], ['averages', 'Averages'],
    ])),
    part('profile.matches', 'Matches'),
    part('profile.heroes', 'Heroes'),
    part('profile.laning', 'Laning', within('profile.laning', [
      ['lane', 'Lane record, farm and fights'], ['versus', 'Your lane vs the enemy lane'], ['best', 'Best lanes'], ['worst', 'Worst lanes'],
    ])),
    part('profile.warding', 'Warding', within('profile.warding', [['numbers', 'Ward numbers'], ['map', 'Ward map']])),
    part('profile.teammates', 'Teammates', within('profile.teammates', [['mates', 'With tracked accounts'], ['heroes', 'Heroes on my team and against me']])),
  ]),
  part('compare', 'Player comparison', within('compare', [['stats', 'Stats'], ['wards', 'Ward maps']])),
  part('tournaments', 'Tournaments', within('tournaments', [
    ['explore', 'Explore tab'], ['search', 'Search tab'], ['list', 'Subscribed tab'], ['teams', 'Teams tab'],
  ])),
  { ...part('league', 'Tournament page', [
    part('league.header', 'Facts'),
    part('league.overview', 'Overview', within('league.overview', [
      ['live', 'Live now'], ['upcoming', 'Upcoming'], ['bracket', 'Bracket'], ['groups', 'Groups and standings'],
    ])),
    part('league.teams', 'Teams'),
    part('league.stats', 'Stats', within('league.stats', [['heroes', 'Heroes'], ['players', 'Players'], ['h2h', 'Head-to-head']])),
    part('league.games', 'Games', within('league.games', [['series', 'Series'], ['latest', 'Latest games']])),
  ]), group: true },
  { ...part('team', 'Team page', [
    part('team.overview', 'Overview', within('team.overview', [['stack', 'Main stack'], ['standins', 'Stand-ins'], ['history', 'Historical players']])),
    part('team.games', 'Games'),
    part('team.players', 'Players'),
    part('team.draft', 'Draft', within('team.draft', [['heroes', 'Heroes in their drafts'], ['roles', 'Roles in their draft']])),
    part('team.general', 'General', within('team.general', [
      ['wards', 'Wards placed'], ['moves', 'First moves'], ['blood', 'First blood'], ['lanes', 'Lanes at 10:00'],
      ['tormentor', 'First Tormentor'], ['runes', 'Wisdom runes'],
    ])),
  ]), group: true },
  { ...part('match', 'Match page', [
    part('match.general', 'General', within('match.general', [['score', 'Scoreboard'], ['picks', 'Pick order'], ['lead', 'Lead'], ['lanes', 'Lanes and buildings']])),
    part('match.draft', 'Draft'),
    part('match.graphs', 'Graphs'),
    part('match.laning', 'Laning'),
    part('match.builds', 'Builds', within('match.builds', [['items', 'Item timeline'], ['skills', 'Skills and talents']])),
    part('match.map', 'Wards and deaths'),
    part('match.fights', 'Teamfights'),
  ]), group: true },
  part('filters', 'Filter panel', within('filters', [
    ['matches', 'Matches'], ['role', 'Role'], ['queue', 'Queue'], ['lobby', 'Lobby'], ['mode', 'Mode'], ['hero', 'Hero'],
    ['time', 'Time'], ['tournament', 'Tournament'],
  ])),
] // prettier-ignore

/** The first of `ids` (tabs, in their order) not hidden under `prefix`; `wanted` when it is shown */
export function shownTab<T extends string>(prefix: string, ids: readonly T[], wanted: T): T {
  return isHidden(`${prefix}.${wanted}`) ? (ids.find((id) => !isHidden(`${prefix}.${id}`)) ?? wanted) : wanted
}
