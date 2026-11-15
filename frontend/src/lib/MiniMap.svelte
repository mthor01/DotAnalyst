<script lang="ts" module>
  // Replay positions are map cells; the image covers cells 64-191 with the Radiant base bottom left.
  // Checked by laying the hero positions of 30 replays over the image: the lanes fall on the lane paths.
  const clamp = (v: number) => Math.min(127, Math.max(0, v))
  export const mapX = (x: number) => clamp(x - 64)
  export const mapY = (y: number) => clamp(191 - y)

  const CLOSE_UP = 48 // cells; a close-up shows at least this much of the 127-cell map
  /** The square of the map that holds these places, with room around them, kept inside the map. */
  export function viewOf(places: { x: number | null; y: number | null }[]) {
    if (!places.length) return { x: 0, y: 0, size: 127 }
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
</script>

<script lang="ts">
  import type { Snippet } from 'svelte'

  type Props = {
    label: string
    /** Shows only a part of the map: an SVG viewBox in map cells. */
    view?: string
    /** When each building fell (a match's `buildings`). With it the map draws the towers, barracks and Ancients. */
    fallen?: { name: string; time: number }[]
    /** The game second the buildings are shown at: one that fell later still stands. Left out, the end of the game. */
    at?: number
    children?: Snippet
  }
  let { label, view = '0 0 127 127', fallen, at = Infinity, children }: Props = $props()

  /** Side of a tower's square in cells: a share of the picture, but small enough on the whole map that a tier-3
   *  tower and the barracks behind it stay apart. */
  const unit = $derived(Math.min(+view.split(' ')[2] * 0.0425, 3))
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

<!-- one unit of the viewBox is one map cell, so marks are placed with mapX/mapY and sized in cells -->
<svg viewBox={view} role="img" aria-label={label}>
  <image href="/minimap.webp" width="127" height="127" opacity="0.8" />
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
  {@render children?.()}
</svg>

<style>
  svg {
    display: block;
    width: 100%;
    max-width: 520px;
    border-radius: 6px;
    background: #000;
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
