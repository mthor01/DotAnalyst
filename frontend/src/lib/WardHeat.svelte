<script lang="ts">
  import type { WardSpot } from './api'
  import MiniMap, { mapX, mapY } from './MiniMap.svelte'

  let { wards, label }: { wards: WardSpot[]; label: string } = $props()

  const SQUARE = 2 // map cells to a side of the squares that tell, on hover, how many wards went there
  const SCALE = 2 // pixels of the heat picture per map cell
  const SPREAD = 2.5 // cells: wide enough that wards for one area (a cliff, a camp's edge) run into one hill
  const LAYERS = { obs: 'Observers', sen: 'Sentries', radiant: 'As Radiant', dire: 'As Dire' }
  // the heat colours, from a lone ward to the busiest spot: [where on the scale, red, green, blue, opacity]
  const RAMP = [
    [0, 140, 0, 20, 0.45],
    [0.25, 210, 30, 30, 0.7],
    [0.5, 245, 110, 20, 0.85],
    [0.75, 255, 200, 40, 0.92],
    [1, 255, 255, 210, 0.97],
  ] // prettier-ignore

  const shownOf = (on: Record<string, boolean>) => wards.filter((w) => on[w.type] && on[w.radiant ? 'radiant' : 'dire'])

  /** The heat picture: every ward adds a small Gaussian hill, and the height is coloured along RAMP. */
  function heat(shown: WardSpot[]) {
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
    const found = new Map<string, { x: number; y: number; obs: number; sen: number }>()
    for (const w of shown) {
      const x = Math.floor(mapX(w.x) / SQUARE) * SQUARE
      const y = Math.floor(mapY(w.y) / SQUARE) * SQUARE
      const s = found.get(`${x} ${y}`) ?? { x, y, obs: 0, sen: 0 }
      s[w.type] += 1
      found.set(`${x} ${y}`, s)
    }
    return [...found.values()]
  }
  const count = (type: string) => wards.filter((w) => w.type === type).length
</script>

<MiniMap label="{label}: {count('obs')} observers and {count('sen')} sentries" layers={LAYERS}>
  {#snippet children(_, on)}
    {@const shown = shownOf(on)}
    <!-- the map is darkened so that the heat stands out from its greens and greys -->
    <rect class="veil" width="127" height="127" />
    {#if shown.length}
      <image href={heat(shown)} width="127" height="127" class="heat" />
    {/if}
    {#each squares(shown) as s (`${s.x} ${s.y}`)}
      <rect class="spot" x={s.x} y={s.y} width={SQUARE} height={SQUARE}>
        <title>Placed here: {s.obs} {s.obs === 1 ? 'observer' : 'observers'}, {s.sen} {s.sen === 1 ? 'sentry' : 'sentries'}</title>
      </rect>
    {/each}
  {/snippet}
</MiniMap>
<p class="legend">
  <span>{count('obs')} observers and {count('sen')} sentries.</span>
  <span class="scale">One ward <i class="ramp"></i> the most wards</span>
  <span>The buttons choose which wards count; hover a spot for its numbers.</span>
</p>

<style>
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
  /* the RAMP of the script, on black like the darkened map */
  .ramp {
    display: inline-block;
    width: 110px;
    height: 10px;
    border-radius: 2px;
    background:
      linear-gradient(90deg, rgb(140 0 20 / 0.45), rgb(210 30 30 / 0.7) 25%, rgb(245 110 20 / 0.85) 50%,
        rgb(255 200 40 / 0.92) 75%, rgb(255 255 210 / 0.97)),
      #000;
  }
</style>
