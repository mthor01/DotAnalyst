<script lang="ts">
  import type { Snippet } from 'svelte'
  import { clock, get, type MatchPlayer } from './api'
  import { heroIcon, heroName } from './constants.svelte'
  import MiniMap, { mapX, mapY, viewOf } from './MiniMap.svelte'

  type Spot = { time: number; player_slot: number; x: number; y: number; alive: boolean }
  type Props = {
    matchId: string
    /** Game seconds; the positions of that time are fetched, they are not part of the match. */
    start: number
    end: number
    players: MatchPlayer[]
    /** Places the picture must hold, such as where heroes died. */
    points: { x: number | null; y: number | null }[]
    /** The hero the playback is about: ringed, kept in the picture all the way, and dead at the end. */
    follow?: number | null
    /** Drawn under the heroes. Gets the game second shown and the width of the picture in map cells. */
    wards: Snippet<[number, number]>
    label: string
  }
  let { matchId, start, end, players, points, follow = null, wards, label }: Props = $props()

  const SPEED = 2 // game seconds per second
  const LEAP = 8 // cells in one second: more than any hero walks, so a teleport, a blink or a respawn
  let spots = $state.raw<Spot[] | null>(null) // null until they arrive
  let error = $state('')
  let at = $state(0) // seconds into the playback, with fractions
  let playing = $state(false)
  const length = $derived(end - start)
  const second = $derived(Math.floor(start + at))

  $effect(() => {
    let current = true
    ;[spots, error, at, playing] = [null, '', 0, false]
    get<Spot[]>(`matches/${matchId}/positions`, `start=${start}&end=${end}`).then(
      (rows) => current && ((spots = rows), (playing = !matchMedia('(prefers-reduced-motion: reduce)').matches)),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  // one clock for everything that moves: the time between two drawn frames moves the playback on
  $effect(() => {
    if (!playing) return
    let last = performance.now()
    let request = requestAnimationFrame(function step(now) {
      at = Math.min(length, at + (Math.max(0, now - last) / 1000) * SPEED)
      last = now
      if (at >= length) playing = false
      else request = requestAnimationFrame(step)
    })
    return () => cancelAnimationFrame(request)
  })

  /** player slot -> its positions, one a second, counted from `start` */
  const tracks = $derived.by(() => {
    const by = new Map<number, Spot[]>(players.map((p) => [p.player_slot, []]))
    for (const s of spots ?? []) {
      const track = by.get(s.player_slot)
      if (track) track[s.time - start] = s
    }
    return by
  })
  /** Where a hero is `at` seconds in. A curve through its positions (Catmull-Rom): with straight lines from second
   *  to second every change of direction is a jerk. A leap is not a path: the hero stays, then is there. */
  function place(track: Spot[], at: number) {
    const i = Math.max(0, Math.min(Math.floor(at), track.length - 2))
    const t = at - i
    const [p1, p2] = [track[i], track[i + 1]]
    if (!p1 || !p2) return p1 ?? p2 ?? null
    const leap = (a: Spot, b: Spot) => Math.hypot(a.x - b.x, a.y - b.y) > LEAP
    if (t >= 1 || leap(p1, p2)) return t < 1 ? p1 : p2
    const p0 = track[i - 1] && !leap(track[i - 1], p1) ? track[i - 1] : p1
    const p3 = track[i + 2] && !leap(p2, track[i + 2]) ? track[i + 2] : p2
    const curve = (a: number, b: number, c: number, d: number) =>
      b + 0.5 * t * (c - a + t * (2 * a - 5 * b + 4 * c - d + t * (3 * (b - c) + d - a)))
    return { x: curve(p0.x, p1.x, p2.x, p3.x), y: curve(p0.y, p1.y, p2.y, p3.y), alive: p1.alive }
  }

  const view = $derived(viewOf([...points, ...(follow === null ? [] : (tracks.get(follow) ?? []))]))
  const icon = $derived(view.size * 0.085)
  /** The followed hero last, so it is drawn on top. */
  const cast = $derived([...players].sort((a, b) => +(a.player_slot === follow) - +(b.player_slot === follow)))
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if !spots}
  <p class="muted">Loading…</p>
{:else}
  <MiniMap label="Positions of the heroes at {clock(second)}, {label}" view="{view.x} {view.y} {view.size} {view.size}">
    {@render wards(second, view.size)}
    {#each cast as p (p.player_slot)}
      {@const spot = place(tracks.get(p.player_slot) ?? [], at)}
      {#if spot}
        <g
          class={p.player_slot < 128 ? 'radiant' : 'dire'}
          class:down={!spot.alive || (p.player_slot === follow && at >= length)}
          transform="translate({mapX(spot.x)} {mapY(spot.y)})"
        >
          <title>{heroName(p.hero_id)}</title>
          {#if p.player_slot === follow}<circle class="halo" r={icon * 0.82} stroke-width={icon * 0.1} />{/if}
          <circle r={icon * 0.62} stroke-width={icon * 0.1} />
          <image href={heroIcon(p.hero_id)} x={-icon / 2} y={-icon / 2} width={icon} height={icon} />
        </g>
      {/if}
    {/each}
  </MiniMap>
  <p class="controls">
    <button class="action" onclick={() => (at >= length && (at = 0), (playing = !playing))}>
      {playing ? 'Pause' : at >= length ? 'Play again' : 'Play'}
    </button>
    <input type="range" min="0" max={length} step="any" bind:value={at} oninput={() => (playing = false)} aria-label="Second of the playback" />
    <span>{clock(second)}</span>
  </p>
{/if}

<style>
  circle {
    fill: var(--page);
  }
  .radiant circle {
    stroke: var(--radiant);
  }
  .dire circle {
    stroke: var(--dire);
  }
  g circle.halo {
    fill: none;
    stroke: #fff;
  }
  .down {
    opacity: 0.3;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 12px;
    max-width: 520px;
    margin: 10px 0 8px;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  .controls button {
    min-width: 9ch;
  }
  .controls input {
    flex: 1;
    margin: 0;
    padding: 0;
  }
  .controls span {
    min-width: 5ch;
    text-align: right;
  }
</style>
