<script lang="ts" module>
  // Replay positions are map cells; the image covers cells 64-191 with the Radiant base bottom left.
  // Checked by laying the hero positions of 30 replays over the image: the lanes fall on the lane paths.
  const clamp = (v: number) => Math.min(127, Math.max(0, v))
  export const mapX = (x: number) => clamp(x - 64)
  export const mapY = (y: number) => clamp(191 - y)

  const CLOSE_UP = 48 // cells; a close-up shows at least this much of the 127-cell map
  const CLOSEST = 12 // cells; as far as the reader can zoom in
  const WHOLE = { x: 0, y: 0, size: 127 }
  /** The square of the map that holds these places, with room around them, kept inside the map. */
  export function viewOf(places: { x: number | null; y: number | null }[]) {
    if (!places.length) return WHOLE
    const xs = places.map((d) => mapX(d.x!))
    const ys = places.map((d) => mapY(d.y!))
    const extent = (vs: number[]) => Math.max(...vs) - Math.min(...vs)
    const size = Math.min(127, Math.max(CLOSE_UP, extent(xs) + 16, extent(ys) + 16))
    const from = (vs: number[]) => Math.min(127 - size, Math.max(0, (Math.min(...vs) + Math.max(...vs) - size) / 2))
    return { x: from(xs), y: from(ys), size }
  }

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
  ] // prettier-ignore
  /** goodguys_tower2_mid -> Radiant tier 2 mid tower */
  function buildingName(name: string) {
    const [side, kind, ...rest] = name.split('_')
    const team = side === 'goodguys' ? 'Radiant' : 'Dire'
    if (kind === 'fort') return `${team} Ancient`
    if (kind.startsWith('tower')) return `${team} tier ${kind.slice(5)} ${rest.join(' ')} tower`.replace('  ', ' ')
    return `${team} ${rest[1]} ${kind} barracks`
  }

  /** Pairs for MiniMap's `toggles`: one button that switches between the two keys, in each key's colour (TINTS) */
  export const SIDES = { radiant: 'Radiant', dire: 'Dire' }
  export const KINDS = { obs: 'Observers', sen: 'Sentries' }
  const TINTS: Record<string, string> = { radiant: 'var(--radiant)', dire: 'var(--dire)', obs: 'var(--series-4)', sen: 'var(--series-1)' }
</script>

<script lang="ts">
  import type { Snippet } from 'svelte'

  type View = { x: number; y: number; size: number }
  type Props = {
    label: string
    /** The square of the map shown at first, in map cells (see viewOf). The reader moves and zooms from there. */
    view?: View
    /** When each building fell (a match's `buildings`). With it the map draws the towers, barracks and Ancients. */
    fallen?: { name: string; time: number }[]
    /** The game second the buildings are shown at: one that fell later still stands. Left out, the end of the game. */
    at?: number
    /** What the reader can show besides the buildings: one dropdown per group, key -> the name of its option. The
     *  first option is chosen at first; the key '' shows every key of its group. */
    layers?: Record<string, string>[]
    /** Pairs the reader switches between, key -> name: one button per pair, its first key shown at first (see
     *  SIDES, KINDS). Only the key shown is on. */
    toggles?: Record<string, string>[]
    /** More controls, in the row of the dropdowns */
    controls?: Snippet
    /** Gets the width of the picture in map cells, to size its marks by so that they stay as large on the screen
     *  when the reader zooms, and which layers are shown. */
    children?: Snippet<[number, Record<string, boolean>]>
    /** No controls and no zooming: the whole map with every layer's first option */
    plain?: boolean
  }
  let { label, view = WHOLE, fallen, at = Infinity, layers = [], toggles = [], controls, children, plain = false }: Props = $props()

  const box = (v: View) => `${v.x} ${v.y} ${v.size} ${v.size}`
  let moved = $state<View | null>(null) // where the reader has taken the picture; null is the view given
  const given = $derived(box(view))
  $effect(() => {
    given // another view given (another fight, another death) starts from that view again
    moved = null
  })
  const shown = $derived(moved ?? view)
  let svg: SVGSVGElement

  function place(x: number, y: number, size: number) {
    const inside = (v: number) => Math.min(127 - size, Math.max(0, v))
    moved = { x: inside(x), y: inside(y), size }
  }
  function zoom(e: WheelEvent) {
    if (plain) return
    const { x, y, size } = shown
    const to = Math.min(127, Math.max(CLOSEST, size * (e.deltaY < 0 ? 0.8 : 1.25)))
    if (to === size) return // at either end the wheel scrolls the page again
    e.preventDefault()
    const frame = svg.getBoundingClientRect()
    // the cell under the pointer stays under it
    place(x + ((e.clientX - frame.left) / frame.width) * (size - to), y + ((e.clientY - frame.top) / frame.height) * (size - to), to)
  }
  let grip: { x: number; y: number } | null = null // where the pointer was at the last step of a drag
  function drag(e: PointerEvent) {
    if (!grip) return
    const cells = shown.size / svg.getBoundingClientRect().width // per pixel
    place(shown.x - (e.clientX - grip.x) * cells, shown.y - (e.clientY - grip.y) * cells, shown.size)
    grip = { x: e.clientX, y: e.clientY }
  }

  let chosen = $state<string[]>([]) // the option of each group the reader picked
  const groups = $derived([...layers, ...(fallen ? [{ buildings: 'Buildings shown', none: 'No buildings' }] : [])])
  // an option no longer offered (another game list, say) falls back to the group's first
  const picked = $derived(groups.map((g, i) => (chosen[i] in g ? chosen[i] : Object.keys(g)[0])))
  let flipped = $state<boolean[]>([]) // the pairs the reader switched to their second key
  const on = $derived({
    ...Object.fromEntries(groups.flatMap((g, i) => Object.keys(g).map((key) => [key, picked[i] === '' || picked[i] === key]))),
    ...Object.fromEntries(toggles.flatMap((t, i) => Object.keys(t).map((key, k) => [key, k === +!!flipped[i]]))),
  })

  /** Side of a tower's square in cells: a share of the picture, but small enough on the whole map that a tier-3
   *  tower and the barracks behind it stay apart. */
  const unit = $derived(Math.min(shown.size * 0.0425, 3))
  const buildings = $derived.by(() => {
    if (!fallen) return []
    const times = new Map<string, number[]>()
    for (const f of fallen) times.set(f.name, [...(times.get(f.name) ?? []), f.time])
    // shortcut: of two tier-4 towers the one listed first is taken to fall first, the log does not say which
    return BUILDINGS.map(([name, x, y]) => {
      const time = times.get(name)?.shift()
      return { name, x, y, down: time !== undefined && time <= at }
    })
  })
</script>

<div class="map">
  {#if !plain}
  <p>
    <span class="controls">
      {@render controls?.()}
      {#each toggles as pair, i}
        {@const [[key, name], [, other]] = flipped[i] ? Object.entries(pair).reverse() : Object.entries(pair)}
        <button class="toggle" style:--tint={TINTS[key]} aria-label="{name}, switch to {other}" title="Switch to {other}"
          onclick={() => (flipped[i] = !flipped[i])}><i></i>{name}</button>
      {/each}
      {#each groups as group, i}
        <select aria-label="What the map shows" value={picked[i]} onchange={(e) => (chosen[i] = e.currentTarget.value)}>
          {#each Object.entries(group) as [key, name] (key)}
            <option value={key}>{name}</option>
          {/each}
        </select>
      {/each}
    </span>
    <button class="action" disabled={!moved || box(moved) === given} onclick={() => (moved = null)}>Reset view</button>
  </p>
  {/if}
  <!-- one unit of the viewBox is one map cell, so marks are placed with mapX/mapY and sized in cells.
       Moving the map is an extra for the mouse: all it shows is in the label and the titles -->
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <svg
    bind:this={svg}
    viewBox={box(shown)}
    role="img"
    aria-label="{label}.{plain ? '' : ' Scroll to zoom, drag to move.'}"
    onwheel={zoom}
    onpointerdown={(e) => plain || ((grip = { x: e.clientX, y: e.clientY }), svg.setPointerCapture(e.pointerId))}
    onpointermove={drag}
    onpointerup={() => (grip = null)}
    onpointercancel={() => (grip = null)}
  >
    <image href="/minimap.webp" width="127" height="127" opacity="0.8" />
    {#if on.buildings}
      {#each buildings as b, i (i)}
        {@const size = unit * (b.name.endsWith('fort') ? 1.8 : b.name.includes('rax') ? 0.76 : 1)}
        <rect
          class={b.name.startsWith('goodguys') ? 'radiant' : 'dire'}
          class:fallen={b.down}
          x={mapX(b.x) - size / 2}
          y={mapY(b.y) - size / 2}
          width={size}
          height={size}
          stroke-width={unit * 0.14}
        >
          <title>{buildingName(b.name)}{b.down ? ', destroyed' : ''}</title>
        </rect>
      {/each}
    {/if}
    {@render children?.(shown.size, on)}
  </svg>
</div>

<style>
  .map {
    max-width: 520px;
  }
  p {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    margin: 0 0 6px;
    font-size: 13px;
  }
  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .controls :global(select) {
    margin-left: 0;
  }
  /* the colour of the key shown fills the dot and edges the button. Global inside .controls so a map's own
     controls snippet can use the same button */
  .controls :global(.toggle) {
    font: inherit;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-width: 8.5em;
    padding: 3px 10px;
    border: 1px solid var(--tint);
    border-radius: 4px;
    background: var(--raised);
    color: var(--text);
    cursor: pointer;
  }
  .controls :global(.toggle i) {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--tint);
  }
  p button:disabled {
    color: var(--muted);
    cursor: default;
  }
  svg {
    display: block;
    width: 100%;
    border-radius: 6px;
    background: #000;
    cursor: grab;
    user-select: none;
  }
  svg:active {
    cursor: grabbing;
  }
  rect {
    stroke: var(--page);
  }
  rect.radiant {
    fill: var(--radiant);
  }
  rect.dire {
    fill: var(--dire);
  }
  rect.fallen {
    fill: none;
    stroke: var(--text-2);
    opacity: 0.6;
  }
</style>
