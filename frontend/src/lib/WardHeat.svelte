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
      <filter id="ward-heat"><feGaussianBlur stdDeviation="0.6" /></filter>
    </defs>
    <!-- the map is darkened so that the glow stands out from its greens and greys -->
    <rect class="veil" width="127" height="127" />
    <g filter="url(#ward-heat)">
      {#each squares(on) as s (`${s.type} ${s.x} ${s.y}`)}
        <!-- a glow wider than its square, so neighbouring squares run together; the square root keeps a spot
             warded twice visible beside one warded twenty times -->
        <circle class={s.type} cx={s.x + SQUARE / 2} cy={s.y + SQUARE / 2} r={SQUARE * 0.8} opacity={0.45 + 0.55 * Math.sqrt(s.heat)}>
          <title>{KIND[s.type]} placed here: {s.n}</title>
        </circle>
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
  .veil {
    fill: #000;
    opacity: 0.5;
    pointer-events: none;
  }
  .legend {
    margin: 8px 0 0;
    max-width: 520px;
  }
</style>
