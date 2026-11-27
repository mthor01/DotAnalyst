<script lang="ts">
  import { TIER_COLOR, liquipedia, tierGroup, type ExploreAnswer, type ExploreLeague } from './leagues'

  // the tournaments of these weeks as bars on one timeline; bars that do not overlap share a row. One only
  // Liquipedia's list knows (no league id yet) links to Liquipedia
  let { entries, league, now }: { entries: ExploreAnswer['calendar']; league: (id: number | string) => ExploreLeague | undefined; now: number } =
    $props()

  const DAY = 86400
  const from = $derived(now - 14 * DAY) // explore.py's CALENDAR_BACK and CALENDAR_AHEAD
  const to = $derived(now + 60 * DAY)
  const at = (t: number) => ((Math.min(Math.max(t, from), to) - from) / (to - from)) * 100
  const ROW = 30

  const rows = $derived.by(() => {
    const ends: number[] = [] // each row's last end
    return [...entries]
      .sort((a, b) => a.start - b.start)
      .map((e) => {
        // a gap of 2 days keeps two bars apart enough for their names
        let row = ends.findIndex((end) => end + 2 * DAY < e.start)
        if (row < 0) row = ends.push(0) - 1
        ends[row] = Math.max(e.end, e.start + DAY)
        return { ...e, row }
      })
  })
  // a label each Monday
  const weeks = $derived.by(() => {
    const first = new Date(from * 1000)
    first.setUTCHours(0, 0, 0, 0)
    first.setUTCDate(first.getUTCDate() + ((8 - first.getUTCDay()) % 7))
    const out: number[] = []
    for (let t = first.getTime() / 1000; t < to; t += 7 * DAY) out.push(t)
    return out
  })
  const label = (t: number) => new Date(t * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
  const span = (s: number, e: number, open: boolean) => `${label(s)} – ${open ? 'still playing' : label(e)}`
</script>

<div class="scroll">
  <div class="timeline" style:height="{28 + Math.max(1, rows.length ? Math.max(...rows.map((r) => r.row)) + 1 : 1) * ROW + 8}px">
    {#each weeks as w (w)}
      <span class="week" style:left="{at(w)}%">{label(w)}</span>
    {/each}
    <span class="today" style:left="{at(now)}%" title="Today"></span>
    {#each rows as e (e.league_id)}
      {@const l = league(e.league_id)}
      {#if l}
        <a
          class="bar"
          class:open={e.open}
          href={l.league_id !== null ? `#league/${l.league_id}` : l.lp_page ? liquipedia(l.lp_page) : undefined}
          target={l.league_id === null ? '_blank' : undefined}
          rel={l.league_id === null ? 'noopener' : undefined}
          title="{l.name}: {span(e.start, e.end, e.open)}"
          style:left="{at(e.start)}%"
          style:width="max(6px, {at(Math.max(e.end, e.start + 86400)) - at(e.start)}%)"
          style:top="{28 + e.row * ROW}px"
          style:--tier={TIER_COLOR[tierGroup(l.lp_tier)]}
        ><span>{l.name}</span></a>
      {/if}
    {/each}
  </div>
</div>

<style>
  .scroll {
    overflow-x: auto;
  }
  .timeline {
    position: relative;
    min-width: 760px;
  }
  .week {
    position: absolute;
    top: 0;
    bottom: 0;
    padding: 2px 0 0 5px;
    border-left: 1px solid var(--grid);
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }
  .today {
    position: absolute;
    top: 18px;
    bottom: 0;
    width: 2px;
    margin-left: -1px;
    background: var(--text);
    opacity: 0.75;
  }
  .bar {
    position: absolute;
    height: 22px;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    padding: 0 8px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--tier) 30%, var(--surface));
    border-left: 3px solid var(--tier);
    color: var(--text);
    font-size: 12px;
    font-weight: 600;
    text-decoration: none;
    overflow: hidden;
  }
  .bar.open {
    /* still playing with no end date: the bar fades out at today */
    mask-image: linear-gradient(to right, #000 70%, transparent);
  }
  .bar:hover,
  .bar:focus-visible {
    background: color-mix(in srgb, var(--tier) 50%, var(--surface));
    z-index: 1;
    overflow: visible;
  }
  .bar span {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .bar:hover span,
  .bar:focus-visible span {
    overflow: visible;
  }
</style>
