<script lang="ts">
  import type { LpBracket, LpMatch, LpOpponent } from './leagues'

  // a bracket tree from Liquipedia: one column per round, each match at the mean height of the matches feeding it
  let { bracket, logo, link }: { bracket: LpBracket; logo: (teamId: number) => string | null; link: (m: LpMatch) => string | null } = $props()

  const BOX_W = 190
  const GAP = 44 // between two columns, where the lines run
  const ROW = 66 // height of one slot
  const BOX_H = 52
  const HEAD = 36 // the round names, two lines at most

  type Placed = { m: LpMatch; x: number; y: number }
  /** Each section's matches with their place; a match no same-section match feeds goes below the one above it */
  function place(rounds: LpBracket['sections'][number]['rounds']) {
    const at = new Map<string, number>()
    const placed: Placed[] = []
    rounds.forEach((r, column) => {
      let floor = -1
      for (const m of r.matches) {
        const fed = (m.feeders ?? []).map((f) => at.get(f)).filter((y) => y !== undefined)
        const y = Math.max(fed.length ? fed.reduce((a, b) => a + b, 0) / fed.length : floor + 1, floor + 1)
        floor = y
        if (m.id) at.set(m.id, y)
        placed.push({ m, x: column * (BOX_W + GAP), y })
      }
    })
    const height = Math.max(0, ...placed.map((p) => p.y)) + 1
    // the lines: from the middle right of each feeder to the middle left of the match it feeds
    const byId = new Map(placed.filter((p) => p.m.id).map((p) => [p.m.id!, p]))
    const lines = placed.flatMap((p) =>
      (p.m.feeders ?? []).flatMap((f) => {
        const from = byId.get(f)
        if (!from) return []
        const [x1, y1, x2, y2] = [from.x + BOX_W, top(from.y) + BOX_H / 2, p.x, top(p.y) + BOX_H / 2]
        const mid = x1 + GAP / 2
        return [`M${x1},${y1} H${mid} V${y2} H${x2}`]
      }),
    )
    return { placed, lines, width: rounds.length * (BOX_W + GAP) - GAP, height: HEAD + height * ROW }
  }
  const top = (y: number) => HEAD + y * ROW + (ROW - BOX_H) / 2
  const SECTION = { upper: 'Upper bracket', lower: 'Lower bracket' }
</script>

{#snippet side(o: LpOpponent, score: number, won: boolean, played: boolean)}
  {@const src = o.team_id ? logo(o.team_id) : null}
  <span class="opponent" class:won class:tbd={!o.name}>
    <span class="logo">{#if src}<img {src} alt="" width="18" height="18" loading="lazy" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden')} />{/if}</span>
    <span class="name" title={o.name ?? 'To be decided'}>{o.name ?? 'TBD'}</span>
    <span class="score">{played ? score : ''}</span>
  </span>
{/snippet}

{#each bracket.sections as section (section.name)}
  {@const { placed, lines, width, height } = place(section.rounds)}
  {#if bracket.sections.length > 1}<h4>{SECTION[section.name]}</h4>{/if}
  <div class="scroll">
    <div class="tree" style:width="{width}px" style:height="{height}px">
      {#each section.rounds as r, column}
        <span class="round" style:left="{column * (BOX_W + GAP)}px" style:width="{BOX_W}px">{r.name}</span>
      {/each}
      <svg {width} {height} aria-hidden="true">
        {#each lines as d}<path {d} />{/each}
      </svg>
      {#each placed as { m, x, y }}
        {@const href = link(m)}
        {@const played = m.maps.some((p) => p.winner !== null)}
        <svelte:element
          this={href ? 'a' : 'div'}
          class="match"
          href={href ?? undefined}
          target={href?.startsWith('http') ? '_blank' : undefined}
          rel={href?.startsWith('http') ? 'noreferrer' : undefined}
          style:left="{x}px"
          style:top="{top(y)}px"
          style:width="{BOX_W}px"
          style:height="{BOX_H}px"
        >
          {@render side(m.opponents[0], m.score[0], m.winner === 0, played)}
          {@render side(m.opponents[1], m.score[1], m.winner === 1, played)}
        </svelte:element>
      {/each}
    </div>
  </div>
{/each}

<style>
  h4 {
    margin: 14px 0 4px;
    color: var(--text-2);
    font-size: 13px;
  }
  .scroll {
    overflow-x: auto;
    padding-bottom: 6px;
  }
  .tree {
    position: relative;
  }
  .round {
    position: absolute;
    top: 0;
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    line-height: 1.25;
  }
  svg {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }
  path {
    fill: none;
    stroke: var(--border);
    stroke-width: 1.5;
  }
  .match {
    position: absolute;
    display: flex;
    flex-direction: column;
    justify-content: center;
    box-sizing: border-box;
    padding: 2px 8px;
    border-radius: 6px;
    background: var(--surface);
    box-shadow: inset 0 0 0 1px var(--border);
    color: var(--text);
    text-decoration: none;
  }
  a.match:hover {
    box-shadow: inset 0 0 0 1px var(--series-1);
  }
  .opponent {
    display: flex;
    align-items: center;
    gap: 6px;
    height: 22px;
    font-size: 13px;
  }
  .logo {
    width: 18px;
    flex: none;
  }
  .logo img {
    display: block;
    object-fit: contain;
  }
  .name {
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .score {
    font-variant-numeric: tabular-nums;
    color: var(--text-2);
  }
  .won .name,
  .won .score {
    font-weight: 700;
    color: var(--text);
  }
  .tbd {
    color: var(--muted);
  }
</style>
