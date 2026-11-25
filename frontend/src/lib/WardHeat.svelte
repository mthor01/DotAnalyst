<script module lang="ts">
  /** What the heatmap shows and how to use it: in the map's own "?" on a page with the whole map, else in the page's */
  export const HOW =
    'Every ward warms the map around its spot, observers in reds and yellows, sentries in blues: dark is a spot warded once, bright the spots warded most, each kind scaled to its own busiest spot. The buttons, dropdowns, timeline and quantity filter choose which wards count. Scroll over the map to zoom (all the way out shows the whole map again), drag to move it, hover a spot for its numbers.'
</script>

<script lang="ts">
  import type { WardSpot } from './api'
  import About from './About.svelte'
  import MiniMap, { KINDS as KIND_NAMES, mapX, mapY } from './MiniMap.svelte'

  /** games: those the wards could come from, warded or not. byGame: wards and games carry `league`, and a dropdown
   *  splits tournament games from the rest */
  type Props = {
    wards: WardSpot[]
    games: { radiant: boolean; win: boolean | number; league?: boolean }[]
    label: string
    byGame?: boolean
    /** Bindable, so that two heatmaps move as one: the timeline, the slider, and MiniMap's moved and chosen */
    periods?: boolean[]
    share?: number
    moved?: { x: number; y: number; size: number } | null
    chosen?: string[]
    /** Only the map with its counts, or only the controls: headed blocks for a .filterbox (app.css), with a Reset view
     *  for the shared zoom; the page then explains the map itself */
    only?: 'map' | 'controls'
    /** false when the page shows the ward counts itself */
    counts?: boolean
  }
  let {
    wards, games, label, byGame = false, only, counts = true,
    periods = $bindable([true, true, true, true, true]), // the stretches of the timeline (PERIODS) switched on
    share = $bindable(0), // percent: only squares warded in at least this share of the chosen games
    moved = $bindable(null), chosen = $bindable([]),
  }: Props = $props() // prettier-ignore
  const id = $props.id()

  const SQUARE = 2 // map cells to a side of the squares that tell, on hover, how many wards went there
  const SCALE = 2 // pixels of the heat picture per map cell
  const SPREAD = 1.5 // cells: wards on the same spot run into one hill, wards a few cells apart stay apart
  const TOGGLES = [{ radiant: 'As Radiant', dire: 'As Dire' }, KIND_NAMES]
  const GAMES = { '': 'All games', league: 'Tournament games', usual: 'Usual matches' }
  const RESULTS = { won: 'Wins', lost: 'Losses' } // buttons like the side's and the kind's, with Both before them
  /** The timeline: ten minutes each, the last open-ended */
  const PERIODS = ['0–10', '10–20', '20–30', '30–40', '40+']
  /** The ten minutes a ward was placed in, as an index of PERIODS; wards before the horn count to the first. */
  const period = (w: WardSpot) => Math.min(PERIODS.length - 1, Math.floor(Math.max(0, w.time) / 600))
  const every = $derived(periods.every(Boolean))
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

  const shownOf = (on: Record<string, boolean>) =>
    wards.filter(
      (w) => on[w.type] && periods[period(w)] && picked(w, on),
    )

  /** Whether a game (or a ward, by its game) is one the side button and the game dropdowns choose */
  const picked = (g: { radiant: boolean; win: boolean | number; league?: boolean }, on: Record<string, boolean>) =>
    on[g.radiant ? 'radiant' : 'dire'] && on[g.win ? 'won' : 'lost'] && (!byGame || on[g.league ? 'league' : 'usual'])
  /** How many games the buttons and dropdowns choose: the timeline picks wards, not games */
  const tally = (on: Record<string, boolean>) => games.filter((g) => picked(g, on)).length
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
  const SHARE_RULE =
    'Shows only the spots (squares of 2 × 2 map cells) warded in at least this share of the chosen games. A spot counts each game once, however many wards went into it. The chosen games are those the result, side and games choices pick, games without a ward included; the timeline does not change them. 0% shows every warded spot.'
</script>

{#snippet timeline()}
  <span class="choice" role="group" aria-label="When the wards were placed, in minutes" title="When the wards were placed, in minutes">
    {#each PERIODS as name, i}
      <button aria-pressed={periods[i]} onclick={() => (periods = periods.map((on, j) => on !== (i === j)))}>{name}</button>
    {/each}
  </span>
{/snippet}
{#snippet all()}
  <button class="action" onclick={() => (periods = PERIODS.map(() => !every))}>{every ? 'All off' : 'All on'}</button>
{/snippet}

<MiniMap bind:moved bind:chosen {only} reset={false} titles={[...(byGame ? ['Games'] : []), 'Result', 'Side', 'Wards']} label="{label}: {count('obs')} observers and {count('sen')} sentries" toggles={[RESULTS, ...TOGGLES]} layers={byGame ? [GAMES] : []}>
  {#snippet children(_, on)}
    {@const of = tally(on)}
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
{#if only === 'controls'}
  <div>
    <div class="head"><h3>Time</h3>{@render all()}</div>
    {@render timeline()}
  </div>
  <div>
    <h3><label for="{id}-share">Quantity filter</label></h3>
    <p class="share boxed"><input id="{id}-share" type="range" min="0" max="50" step="1" bind:value={share} /><b>{share ? `${share}%` : 'Every spot'}</b><About>{SHARE_RULE}</About></p>
  </div>
  <!-- the map is shown whole at first, so any move is one to undo -->
  <button class="action" disabled={!moved || moved.size >= 127} onclick={() => (moved = null)}>Reset view</button>
{:else if only !== 'map'}
<p class="timeline">{@render timeline()}{@render all()}</p>
<p class="share">
  <label for="{id}-share">Quantity filter</label>
  <input id="{id}-share" type="range" min="0" max="50" step="1" bind:value={share} />
  <b>{share ? `${share}%` : 'Every spot'}</b><About>{SHARE_RULE}</About>
</p>
{/if}
{#if only !== 'controls' && (only !== 'map' || counts)}
<p class="legend">
  {#if counts}<span>{count('obs')} observers and {count('sen')} sentries.</span>{/if}
  {#if !only}
    <About>{HOW}</About>
  {/if}
</p>
{/if}

<style>
  .share {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    max-width: var(--map-max, 520px);
    margin: 8px 0 0;
    font-size: 13px;
    color: var(--text-2);
  }
  .share input {
    flex: 1;
    min-width: 80px;
    margin: 0;
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .head h3 {
    margin: 0;
  }
  .head .action {
    padding: 2px 10px;
  }
  .share.boxed {
    max-width: none;
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
    flex: 1 0 260px;
    flex-wrap: nowrap;
    max-width: 380px;
  }
  .choice button {
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    padding: 4px 6px;
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
    max-width: var(--map-max, 520px);
  }
</style>
