<script lang="ts" module>
  // Replay positions are map cells; the image covers cells 64-191 with the Radiant base bottom left.
  // Checked by laying the hero positions of 30 replays over the image: the lanes fall on the lane paths.
  const clamp = (v: number) => Math.min(127, Math.max(0, v))
  export const mapX = (x: number) => clamp(x - 64)
  export const mapY = (y: number) => clamp(191 - y)
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
