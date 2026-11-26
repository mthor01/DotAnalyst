<script lang="ts">
  import type { LpBracket, LpMatch, LpOpponent } from './leagues'

  // a bracket tree from Liquipedia: one column per round, each match at the mean height of the matches feeding it;
  // a match with games played opens them (onpick)
  let { bracket, logo, onpick }: { bracket: LpBracket; logo: (teamId: number) => string | null; onpick: (m: LpMatch) => void } = $props()

  const BOX_W = 200
  const GAP = 48 // between two columns, where the lines run
  const ROW = 74 // height of one slot
  const BOX_H = 58
  const HEAD = 30 // the round names

  type Placed = { m: LpMatch; x: number; y: number }
  /** Each section's matches with their place. A round's matches go in the order of the matches feeding them, so the
   * lines never cross; a match no same-section match feeds keeps its place in the list, below the one above it. */
  function place(rounds: LpBracket['sections'][number]['rounds']) {
    const at = new Map<string, number>()
    const placed: Placed[] = []
    rounds.forEach((r, column) => {
      const keyed = r.matches.map((m, i) => {
        const fed = (m.feeders ?? []).map((f) => at.get(f)).filter((y) => y !== undefined)
        return { m, fed, key: fed.length ? fed.reduce((a, b) => a + b, 0) / fed.length : i }
      })
      keyed.sort((a, b) => a.key - b.key)
      let floor = -1
      for (const { m, fed, key } of keyed) {
        const y = Math.max(fed.length ? key : floor + 1, floor + 1)
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
  // under an "Upper bracket" heading, "Upper Bracket Semifinals" says no more than "Semifinals"
  const roundName = (name: string, split: boolean) => (split ? name.replace(/^(upper|lower) bracket /i, '') : name)
  const playedAny = (m: LpMatch) => m.maps.some((p) => p.match_id || p.winner !== null)
</script>

{#snippet side(o: LpOpponent, score: number, won: boolean, lost: boolean, played: boolean)}
  {@const src = o.team_id ? logo(o.team_id) : null}
  <span class="opponent" class:won class:lost class:tbd={!o.name}>
    <span class="logo">{#if src}<img {src} alt="" width="20" height="20" loading="lazy" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden')} />{/if}</span>
    <span class="name" title={o.name ?? 'To be decided'}>{o.name ?? 'TBD'}</span>
    <span class="score">{played ? score : ''}</span>
  </span>
{/snippet}

{#each bracket.sections as section (section.name)}
  {@const { placed, lines, width, height } = place(section.rounds)}
  {@const split = bracket.sections.length > 1}
  {#if split}<h4>{SECTION[section.name]}</h4>{/if}
  <div class="scroll">
    <div class="tree" style:width="{width}px" style:height="{height}px">
      {#each section.rounds as r, column}
        <span class="round" style:left="{column * (BOX_W + GAP)}px" style:width="{BOX_W}px" title={r.name}>{roundName(r.name, split)}</span>
      {/each}
      <svg {width} {height} aria-hidden="true">
        {#each lines as d}<path {d} />{/each}
      </svg>
      {#each placed as { m, x, y }}
        {@const played = playedAny(m)}
        {@const decided = m.winner !== null}
        <svelte:element
          this={played ? 'button' : 'div'}
          class="match"
          type={played ? 'button' : undefined}
          title={played ? 'Show the games' : undefined}
          onclick={played ? () => onpick(m) : undefined}
          role={played ? undefined : 'group'}
          style:left="{x}px"
          style:top="{top(y)}px"
          style:width="{BOX_W}px"
          style:height="{BOX_H}px"
        >
          {@render side(m.opponents[0], m.score[0], m.winner === 0, decided && m.winner !== 0, played)}
          {@render side(m.opponents[1], m.score[1], m.winner === 1, decided && m.winner !== 1, played)}
        </svelte:element>
      {/each}
    </div>
  </div>
{/each}

<style>
  h4 {
    margin: 4px 0 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
  }
  h4:not(:first-child) {
    margin-top: 22px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }
  .scroll {
    overflow-x: auto;
    padding-bottom: 4px;
  }
  .tree {
    position: relative;
  }
  .round {
    position: absolute;
    top: 0;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  svg {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }
  path {
    fill: none;
    stroke: var(--axis);
    stroke-width: 2;
    stroke-linejoin: round;
  }
  .match {
    position: absolute;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface);
    color: var(--text);
    font: inherit;
    text-align: left;
  }
  button.match {
    cursor: pointer;
  }
  button.match:hover,
  button.match:focus-visible {
    border-color: var(--series-1);
    outline: none;
  }
  .opponent {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-height: 0;
    padding-left: 8px;
    font-size: 13px;
    color: var(--text-2);
  }
  .opponent + .opponent {
    border-top: 1px solid var(--border);
  }
  .logo {
    width: 20px;
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
    align-self: stretch;
    display: grid;
    place-items: center;
    width: 30px;
    flex: none;
    background: var(--raised);
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }
  .won {
    color: var(--text);
    font-weight: 600;
  }
  .won .score {
    background: color-mix(in srgb, var(--series-1) 35%, var(--surface));
    color: var(--text);
  }
  .lost {
    color: var(--muted);
  }
  .tbd .name {
    color: var(--muted);
    font-style: italic;
  }
</style>
