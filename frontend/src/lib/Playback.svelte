<script lang="ts">
  import type { Snippet } from 'svelte'
  import { clock, get, type MatchPlayer } from './api'
  import { heroIcon, heroName } from './constants.svelte'
  import MiniMap, { mapX, mapY, viewOf } from './MiniMap.svelte'

  type Spot = { time: number; player_slot: number; x: number; y: number; alive: boolean }
  type Fallen = { name: string; time: number }

  // Where each building stands, in map cells: the centre of the circle melee heroes stand on while hitting it, fitted
  // over 228 replays of the November 2026 map. The two tier-4 towers of a side share one name.
  const BUILDINGS: [string, number, number][] = [
    ['goodguys_tower1_top', 78.7, 144.6], ['goodguys_tower2_top', 78.1, 122.6], ['goodguys_tower3_top', 77.1, 102.3],
    ['goodguys_tower1_mid', 117.7, 118.7], ['goodguys_tower2_mid', 104.1, 106.3], ['goodguys_tower3_mid', 92.5, 96.5],
    ['goodguys_tower1_bot', 166.1, 79.5], ['goodguys_tower2_bot', 126.2, 79.1], ['goodguys_tower3_bot', 98.3, 80.7],
    ['goodguys_melee_rax_top', 78.2, 99.7], ['goodguys_range_rax_top', 75.5, 99.4],
    ['goodguys_melee_rax_mid', 92.1, 94.1], ['goodguys_range_rax_mid', 90.5, 96.1],
    ['goodguys_melee_rax_bot', 95.5, 79.1], ['goodguys_range_rax_bot', 96.0, 81.7],
    ['goodguys_tower4', 84.0, 91.3], ['goodguys_tower4', 86.9, 88.0], ['goodguys_fort', 83.6, 87.5],
    ['badguys_tower1_top', 86.6, 173.5], ['badguys_tower2_top', 126.1, 174.7], ['badguys_tower3_top', 154.7, 172.7],
    ['badguys_tower1_mid', 130.5, 131.2], ['badguys_tower2_mid', 146.8, 143.6], ['badguys_tower3_mid', 160.7, 156.4],
    ['badguys_tower1_bot', 177.0, 108.7], ['badguys_tower2_bot', 177.4, 129.1], ['badguys_tower3_bot', 177.1, 150.9],
    ['badguys_melee_rax_top', 156.6, 171.1], ['badguys_range_rax_top', 156.7, 174.1],
    ['badguys_melee_rax_mid', 163.1, 156.9], ['badguys_range_rax_mid', 160.9, 158.7],
    ['badguys_melee_rax_bot', 178.1, 153.3], ['badguys_range_rax_bot', 175.7, 153.2],
    ['badguys_tower4', 165.8, 164.8], ['badguys_tower4', 169.0, 161.7], ['badguys_fort', 169.2, 165.5],
  ]
  /** goodguys_tower2_mid -> Radiant tier 2 mid tower */
  function buildingName(name: string) {
    const [side, kind, ...rest] = name.split('_')
    const team = side === 'goodguys' ? 'Radiant' : 'Dire'
    if (kind === 'fort') return `${team} Ancient`
    if (kind.startsWith('tower')) return `${team} tier ${kind.slice(5)} ${rest.join(' ')} tower`.replace('  ', ' ')
    return `${team} ${rest[1]} ${kind} barracks`
  }
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
  let fallen = $state.raw<Fallen[]>([])
  let error = $state('')
  let at = $state(0) // seconds into the playback, with fractions
  let playing = $state(false)
  const length = $derived(end - start)
  const second = $derived(Math.floor(start + at))

  $effect(() => {
    let current = true
    ;[spots, error, at, playing] = [null, '', 0, false]
    get<{ heroes: Spot[]; fallen: Fallen[] }>(`matches/${matchId}/positions`, `start=${start}&end=${end}`).then(
      (got) =>
        current &&
        ((spots = got.heroes), (fallen = got.fallen), (playing = !matchMedia('(prefers-reduced-motion: reduce)').matches)),
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

  /** Every building, and whether it has fallen by the second shown. */
  const buildings = $derived.by(() => {
    const times = new Map<string, number[]>()
    for (const f of fallen) {
      const name = f.name.replace('npc_dota_', '')
      times.set(name, [...(times.get(name) ?? []), f.time])
    }
    // shortcut: of two tier-4 towers the one listed first is taken to fall first, the log does not say which
    return BUILDINGS.map(([name, x, y]) => {
      const time = times.get(name)?.shift()
      return { name, x, y, down: time !== undefined && time <= second }
    })
  })

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
    {#each buildings as b, i (i)}
      {@const size = icon * (b.name.endsWith('fort') ? 0.9 : b.name.includes('rax') ? 0.38 : 0.5)}
      <rect
        class="building {b.name.startsWith('goodguys') ? 'radiant' : 'dire'}"
        class:fallen={b.down}
        x={mapX(b.x) - size / 2}
        y={mapY(b.y) - size / 2}
        width={size}
        height={size}
        stroke-width={icon * 0.07}
      >
        <title>{buildingName(b.name)}{b.down ? ', destroyed' : ''}</title>
      </rect>
    {/each}
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
  .building {
    stroke: var(--page);
  }
  .building.radiant {
    fill: var(--radiant);
  }
  .building.dire {
    fill: var(--dire);
  }
  .building.fallen {
    fill: none;
    stroke: var(--text-2);
    opacity: 0.6;
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
