<script lang="ts">
  import type { WardSpot } from './api'
  import MiniMap, { KINDS as KIND_NAMES, mapX, mapY } from './MiniMap.svelte'

  /** games: those the wards could come from, warded or not. byGame: wards and games carry `league`, and a dropdown
   *  splits tournament games from the rest */
  let { wards, games, label, byGame = false }: { wards: WardSpot[]; games: { radiant: boolean; win: boolean | number; league?: boolean }[]; label: string; byGame?: boolean } = $props()

  const SQUARE = 2 // map cells to a side of the squares that tell, on hover, how many wards went there
  const SCALE = 2 // pixels of the heat picture per map cell
  const SPREAD = 1.5 // cells: wards on the same spot run into one hill, wards a few cells apart stay apart
  const TOGGLES = [{ radiant: 'As Radiant', dire: 'As Dire' }, KIND_NAMES]
  const GAMES = { '': 'All games', league: 'Tournament games', usual: 'Usual matches' }
  const RESULTS = { '': 'Wins and losses', won: 'Wins', lost: 'Losses' }
  /** The timeline: ten minutes each, the last open-ended */
  const PERIODS = ['0–10', '10–20', '20–30', '30–40', '40+']
  /** The ten minutes a ward was placed in, as an index of PERIODS; wards before the horn count to the first. */
  const period = (w: WardSpot) => Math.min(PERIODS.length - 1, Math.floor(Math.max(0, w.time) / 600))
  let periods = $state(PERIODS.map(() => true)) // the stretches of the timeline switched on
  const every = $derived(periods.every(Boolean))
  let share = $state(0) // percent: only squares warded in at least this share of the chosen games
  // the heat colours of each kind, from a lone ward to its busiest spot: [where on the scale, red, green, blue, opacity]
  const RAMPS = {
    obs: [
      [0, 140, 0, 20, 0.45],
      [0.25, 210, 30, 30, 0.7],
      [0.5, 245, 110, 20, 0.85],
      [0.75, 255, 200, 40, 0.92],
      [1, 255, 255, 210, 0.97],
    ],
    sen: [
      [0, 10, 30, 140, 0.45],
      [0.25, 20, 80, 220, 0.7],
      [0.5, 40, 150, 250, 0.85],
      [0.75, 110, 210, 255, 0.92],
      [1, 225, 245, 255, 0.97],
    ],
  } // prettier-ignore
  const KINDS = ['obs', 'sen'] as const
  /** The legend's strip of a ramp, on black like the darkened map */
  const strip = (ramp: number[][]) =>
    `linear-gradient(90deg, ${ramp.map(([t, r, g, b, a]) => `rgb(${r} ${g} ${b} / ${a}) ${t * 100}%`).join(', ')}), #000`

  const shownOf = (on: Record<string, boolean>) =>
    wards.filter(
      (w) => on[w.type] && periods[period(w)] && picked(w, on),
    )

  /** Whether a game (or a ward, by its game) is one the side button and the game dropdowns choose */
  const picked = (g: { radiant: boolean; win: boolean | number; league?: boolean }, on: Record<string, boolean>) =>
    on[g.radiant ? 'radiant' : 'dire'] && on[g.win ? 'won' : 'lost'] && (!byGame || on[g.league ? 'league' : 'usual'])
  /** How many games the buttons and dropdowns choose: the timeline picks wards, not games */
  const chosen = (on: Record<string, boolean>) => games.filter((g) => picked(g, on)).length
  const square = (w: WardSpot) => `${Math.floor(mapX(w.x) / SQUARE) * SQUARE} ${Math.floor(mapY(w.y) / SQUARE) * SQUARE}`
  /** Only the wards in squares warded in at least the slider's share of the `of` games */
  function common(shown: WardSpot[], of: number) {
    const games = new Map<string, Set<number>>()
    for (const w of shown) games.set(square(w), (games.get(square(w)) ?? new Set()).add(w.match_id))
    return shown.filter((w) => games.get(square(w))!.size >= (share / 100) * of)
  }

  /** The heat picture of one kind: every ward adds a small Gaussian hill, and the height is coloured along the ramp. */
  function heat(shown: WardSpot[], RAMP: number[][]) {
    const size = 127 * SCALE
    const grid = new Float32Array(size * size)
    const sigma = SPREAD * SCALE
    const reach = Math.ceil(3 * sigma)
    for (const w of shown) {
      const cx = mapX(w.x) * SCALE
      const cy = mapY(w.y) * SCALE
      for (let y = Math.max(0, Math.floor(cy - reach)); y <= Math.min(size - 1, cy + reach); y++)
        for (let x = Math.max(0, Math.floor(cx - reach)); x <= Math.min(size - 1, cx + reach); x++)
          grid[y * size + x] += Math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * sigma * sigma))
    }
    let most = 0
    for (const v of grid) most = Math.max(most, v)
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = size
    const context = canvas.getContext('2d')!
    const image = context.createImageData(size, size)
    for (let i = 0; i < grid.length; i++) {
      if (grid[i] < 0.05) continue // the far edge of a hill: left clear, so the map shows
      // the square root keeps a spot warded once visible beside one warded thirty times
      const t = Math.sqrt(grid[i] / most)
      const j = RAMP.findIndex((stop) => stop[0] >= t)
      const [t0, ...a] = RAMP[Math.max(0, j - 1)]
      const [t1, ...b] = RAMP[j]
      const f = t1 > t0 ? (t - t0) / (t1 - t0) : 1
      // the edge of a hill fades in rather than stopping at a hard line
      const fade = Math.min(1, grid[i] / 0.3)
      for (let k = 0; k < 3; k++) image.data[i * 4 + k] = a[k] + f * (b[k] - a[k])
      image.data[i * 4 + 3] = 255 * fade * (a[3] + f * (b[3] - a[3]))
    }
    context.putImageData(image, 0, 0)
    return canvas.toDataURL()
  }

  /** The squares with wards in them, for the counts on hover. */
  function squares(shown: WardSpot[]) {
    const found = new Map<string, { x: number; y: number; obs: number; sen: number; games: Set<number> }>()
    for (const w of shown) {
      const [x, y] = square(w).split(' ').map(Number)
      const s = found.get(square(w)) ?? { x, y, obs: 0, sen: 0, games: new Set() }
      s[w.type] += 1
      s.games.add(w.match_id)
      found.set(square(w), s)
    }
    return [...found.values()]
  }
  const count = (type: string) => wards.filter((w) => w.type === type).length
</script>

<MiniMap reset={false} label="{label}: {count('obs')} observers and {count('sen')} sentries" toggles={TOGGLES} layers={[...(byGame ? [GAMES] : []), RESULTS]}>
  {#snippet children(_, on)}
    {@const of = chosen(on)}
    {@const shown = common(shownOf(on), of)}
    <!-- the map is darkened so that the heat stands out from its greens and greys -->
    <rect class="veil" width="127" height="127" />
    <!-- one picture per kind, each scaled to its own busiest spot; sentries on top, as there are fewer -->
    {#each KINDS as kind}
      {@const these = shown.filter((w) => w.type === kind)}
      {#if these.length}
        <image href={heat(these, RAMPS[kind])} width="127" height="127" class="heat" />
      {/if}
    {/each}
    {#each squares(shown) as s (`${s.x} ${s.y}`)}
      <rect class="spot" x={s.x} y={s.y} width={SQUARE} height={SQUARE}>
        <!-- one string: in SVG, Svelte drops the spaces between expressions -->
        <title>{`Placed here: ${s.obs} ${s.obs === 1 ? 'observer' : 'observers'}, ${s.sen} ${s.sen === 1 ? 'sentry' : 'sentries'}, in ${s.games.size} of ${of} games`}</title>
      </rect>
    {/each}
  {/snippet}
</MiniMap>
<p class="timeline">
  <span class="choice" role="group" aria-label="When the wards were placed, in minutes">
    {#each PERIODS as name, i}
      <button aria-pressed={periods[i]} onclick={() => (periods[i] = !periods[i])}>{name}</button>
    {/each}
  </span>
  <button class="action" onclick={() => (periods = PERIODS.map(() => !every))}>{every ? 'All off' : 'All on'}</button>
  <span class="unit">minutes</span>
</p>
<label class="share" title="Only the spots warded in at least this share of the chosen games">
  Min % games warded
  <input type="range" min="0" max="50" step="1" bind:value={share} />
  <b>{share ? `${share}%` : 'Every spot'}</b>
</label>
<p class="legend">
  <span>{count('obs')} observers and {count('sen')} sentries.</span>
  {#each KINDS as kind}
    <span class="scale">{KIND_NAMES[kind]}: one <i class="ramp" style:background={strip(RAMPS[kind])}></i> the most</span>
  {/each}
  <span>The buttons, dropdowns, slider and timeline choose which wards count; hover a spot for its numbers.</span>
</p>

<style>
  .share {
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: 520px;
    margin: 8px 0 0;
    font-size: 13px;
    color: var(--text-2);
  }
  .share input {
    flex: 1;
    margin: 0;
  }
  .share b {
    min-width: 9ch;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .timeline {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin: 8px 0 0;
    font-size: 13px;
  }
  .choice {
    flex: 1;
    max-width: 380px;
  }
  .choice button {
    flex: 1;
    padding: 4px 6px;
  }
  .unit {
    color: var(--muted);
  }
  .veil {
    fill: #000;
    opacity: 0.55;
    pointer-events: none;
  }
  .heat {
    pointer-events: none;
  }
  .spot {
    fill: transparent;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 14px;
    margin: 8px 0 0;
    max-width: 520px;
  }
  .scale {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .ramp {
    display: inline-block;
    width: 90px;
    height: 10px;
    border-radius: 2px;
  }
</style>
