import { get, type Progress } from './api'

/** What the poller is doing, shared by the progress bar and the replay signs in the game lists. Null until loaded. */
export const progress = $state<{ now: Progress | null }>({ now: null })

/** Asks the server every few seconds while the page is open; returns the function that stops it. */
export function follow(seconds = 3): () => void {
  const load = () => get<Progress>('progress').then((found) => (progress.now = found), () => {}) // offline: keep the last
  load()
  const timer = setInterval(load, seconds * 1000)
  return () => clearInterval(timer)
}

/** What a game list shows in its Replay column. `state` is null for a league game not stored as a match yet. */
export function replaySign(match_id: number, state: string | null, start_time: number): 'parsed' | 'working' | 'waiting' | 'none' {
  if (state === 'parsed') return 'parsed'
  const now = progress.now
  if (now?.working.includes(match_id)) return 'working'
  // the poller's own rule (poll.wanted): asked for by hand, or recent enough that Valve may still have it
  const recent = start_time > (now?.now ?? Date.now() / 1000) - (now?.max_age_days ?? 0) * 86400
  return state === 'pending' || ((state === 'none' || state === null) && recent) ? 'waiting' : 'none'
}
