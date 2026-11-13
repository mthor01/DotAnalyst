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
</script>

<script lang="ts">
  import type { Snippet } from 'svelte'

  /** `view` shows only a part of the map: an SVG viewBox in map cells. */
  let { label, view = '0 0 127 127', children }: { label: string; view?: string; children: Snippet } = $props()
</script>

<!-- one unit of the viewBox is one map cell, so marks are placed with mapX/mapY and sized in cells -->
<svg viewBox={view} role="img" aria-label={label}>
  <image href="/minimap.webp" width="127" height="127" opacity="0.8" />
  {@render children()}
</svg>

<style>
  svg {
    display: block;
    width: 100%;
    max-width: 520px;
    border-radius: 6px;
    background: #000;
  }
</style>
