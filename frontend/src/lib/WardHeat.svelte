<script lang="ts">
  import type { WardSpot } from './api'
  import MiniMap, { mapX, mapY } from './MiniMap.svelte'

  let { wards, label }: { wards: WardSpot[]; label: string } = $props()

  const SQUARE = 2 // map cells to a side: wards for the same spot land within a cell or two of each other
  const LAYERS = { obs: 'Observers', sen: 'Sentries', radiant: 'As Radiant', dire: 'As Dire' }
  const KIND = { obs: 'Observers', sen: 'Sentries' }

  /** The squares of the map with wards of the shown kinds and sides in them. `heat` is 1 for the fullest square. */
  function squares(on: Record<string, boolean>) {
    const found = new Map<string, { type: WardSpot['type']; x: number; y: number; n: number }>()
    for (const w of wards) {
      if (!on[w.type] || !on[w.radiant ? 'radiant' : 'dire']) continue
      const x = Math.floor(mapX(w.x) / SQUARE) * SQUARE
      const y = Math.floor(mapY(w.y) / SQUARE) * SQUARE
      const key = `${w.type} ${x} ${y}`
      found.set(key, { type: w.type, x, y, n: (found.get(key)?.n ?? 0) + 1 })
    }
    const most = Math.max(1, ...[...found.values()].map((s) => s.n))
    return [...found.values()].map((s) => ({ ...s, heat: s.n / most }))
  }
  const count = (type: string) => wards.filter((w) => w.type === type).length
</script>

<MiniMap label="{label}: {count('obs')} observers and {count('sen')} sentries" layers={LAYERS}>
  {#snippet children(_, on)}
    <defs>
      <filter id="ward-heat"><feGaussianBlur stdDeviation="0.5" /></filter>
    </defs>
    <g filter="url(#ward-heat)">
      {#each squares(on) as s (`${s.type} ${s.x} ${s.y}`)}
        <!-- the square root keeps a spot warded twice visible beside one warded twenty times -->
        <rect class={s.type} x={s.x} y={s.y} width={SQUARE} height={SQUARE} opacity={0.3 + 0.7 * Math.sqrt(s.heat)}>
          <title>{KIND[s.type]} placed here: {s.n}</title>
        </rect>
      {/each}
    </g>
  {/snippet}
</MiniMap>
<p class="legend">
  <span><i class="swatch obs"></i>{count('obs')} observers</span>
  <span><i class="swatch sen"></i>{count('sen')} sentries</span>
  <span>The stronger the colour, the more wards went there.</span>
</p>

<style>
  /* the wards' own colours in the game: observers yellow, sentries blue */
  .obs {
    fill: var(--series-4);
    background: var(--series-4);
  }
  .sen {
    fill: var(--series-1);
    background: var(--series-1);
  }
  .legend {
    margin: 8px 0 0;
    max-width: 520px;
  }
</style>
