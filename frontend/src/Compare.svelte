<script lang="ts">
  import { untrack } from 'svelte'
  import { METRICS, get, percent, queryFor, type Account, type MatchRow, type MetricAverage, type TeammateRow, type WardSpot } from './lib/api'
  import WardHeat from './lib/WardHeat.svelte'

  let { query, accounts }: { query: string; accounts: Account[] } = $props()
  // the two accounts compared, the first two tracked ones at first
  let chosen = $state(untrack(() => [accounts[0]?.account_id, accounts[1]?.account_id ?? accounts[0]?.account_id]))
  let together = $state<TeammateRow | undefined>()
  type Side = { matches: MatchRow[]; wards: WardSpot[]; averages: Record<string, MetricAverage> }
  let sides = $state.raw<Side[]>([])
  let error = $state('')
  // what both ward maps show, so that every button, dropdown, slider and zoom moves the two together
  let maps = $state({ periods: [true, true, true, true, true], share: 0, chosen: [] as string[], flipped: [] as boolean[], moved: null })

  $effect(() => {
    let current = true
    const [a, b] = chosen
    if (a === undefined || b === undefined) return
    const side = (id: number) =>
      Promise.all([
        get<MatchRow[]>('matches', queryFor(query, id)),
        get<WardSpot[]>('wards', queryFor(query, id)),
        get<MetricAverage[]>('metric-averages', queryFor(query, id)),
      ]).then(([matches, wards, m]) => ({ matches, wards, averages: Object.fromEntries(m.map((r) => [r.name, r])) }))
    Promise.all([get<TeammateRow[]>('teammates', queryFor(query, a)), side(a), side(b)]).then(
      ([t, ...found]) => current && ((together = t.find((r) => r.account_id === b)), (sides = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const account = (id: number | undefined) => accounts.find((a) => a.account_id === id)
  const mean = (rows: MatchRow[], value: (r: MatchRow) => number) =>
    rows.length ? rows.reduce((sum, r) => sum + value(r), 0) / rows.length : undefined
  const fixed = (digits: number) => (v: number) => v.toFixed(digits)
  /** The rows of the comparison: `lower` when less is better, `count` when neither is (only how much was seen) */
  type Row = { label: string; of: (s: Side) => number | undefined; show: (v: number) => string; lower?: boolean; count?: boolean; title?: (s: Side) => string }
  const ROWS: Row[] = [
    { label: 'Matches', of: (s) => s.matches.length, show: String, count: true },
    { label: 'Win rate', of: (s) => mean(s.matches, (r) => r.win), show: (v) => `${Math.round(100 * v)}%` },
    { label: 'Kills', of: (s) => mean(s.matches, (r) => r.kills), show: fixed(1) },
    { label: 'Deaths', of: (s) => mean(s.matches, (r) => r.deaths), show: fixed(1), lower: true },
    { label: 'Assists', of: (s) => mean(s.matches, (r) => r.assists), show: fixed(1) },
    { label: 'Gold per minute', of: (s) => mean(s.matches, (r) => r.gold_per_min), show: fixed(0) },
    { label: 'Experience per minute', of: (s) => mean(s.matches, (r) => r.xp_per_min), show: fixed(0) },
    // every parsed match of an account has a kill participation, so its count is the number of parsed matches
    { label: 'Parsed matches', of: (s) => s.averages.kill_participation?.matches ?? 0, show: String, count: true },
    ...METRICS.map((m) => ({
      label: m.label,
      of: (s: Side) => s.averages[m.name]?.average,
      show: m.show,
      lower: m.name === 'deaths_outside_fights',
      title: (s: Side) => `${s.averages[m.name]?.matches ?? 0} parsed matches`,
    })),
  ] // prettier-ignore
  /** 'better', 'worse' or '' for side i of a row: equal values, a missing one and counts are neither */
  function verdict(row: Row, i: number) {
    const [a, b] = sides.map(row.of)
    if (row.count || a === undefined || b === undefined || row.show(a) === row.show(b)) return ''
    const first = row.lower ? a < b : a > b
    return first === (i === 0) ? 'better' : 'worse'
  }
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else}
  <div class="duel">
    <header class="heads">
      {#each [0, 1] as i}
        {@const a = account(chosen[i])}
        <div class="head" class:right={i === 1}>
          {#if a?.avatar}<img class="avatar" src={a.avatar} alt="" width="56" height="56" />{/if}
          <!-- the name is the picker: click it to compare another account -->
          <select class="name" aria-label={i ? 'Second account' : 'First account'} title="Click to compare another account" bind:value={chosen[i]}>
            {#each accounts as o (o.account_id)}<option value={o.account_id}>{o.label ?? o.account_id}</option>{/each}
          </select>
        </div>
        {#if i === 0}<span class="vs">vs</span>{/if}
      {/each}
    </header>

    {#if chosen[0] !== chosen[1]}
      <p class="muted together">
        {#if together}
          On the same team in {together.games} matches, won {together.wins} ({percent(together.wins, together.games)}%).
        {:else}
          Never on the same team for these filters.
        {/if}
      </p>
    {/if}

    {#if sides.length === 2}
      <div class="card stats">
        {#each ROWS as row (row.label)}
          {#each [0, 1] as i}
            {@const v = row.of(sides[i])}
            <span class="value {verdict(row, i)}" class:right={i === 1} title={row.title?.(sides[i])}>{v === undefined ? '–' : row.show(v)}</span>
            {#if i === 0}<span class="stat">{row.label}</span>{/if}
          {/each}
        {/each}
      </div>
      <p class="muted">
        Green is the better of the two, red the worse. The replay numbers average each account's matches with a parsed
        replay, the rest every match the filters keep; the games together count every stored match.
      </p>

      <h2>Wards</h2>
      <div class="maps">
        {#each [0, 1] as i}
          {@const a = account(chosen[i])}
          <div class="card">
            <WardHeat
              wards={sides[i].wards}
              games={sides[i].matches.filter((r) => r.replay_state === 'parsed')}
              label={`${a?.label ?? chosen[i]}'s wards`}
              bind:periods={maps.periods}
              bind:share={maps.share}
              bind:chosen={maps.chosen}
              bind:flipped={maps.flipped}
              bind:moved={maps.moved}
            />
          </div>
        {/each}
      </div>
      <p class="muted">The two maps move together: every button, dropdown, slider and zoom applies to both.</p>
    {/if}
  </div>
{/if}

<style>
  /* the same columns as the stats below, so each name stands over its numbers */
  .heads,
  .stats {
    display: grid;
    grid-template-columns: 1fr minmax(auto, 340px) 1fr;
    gap: 0 16px;
  }
  .heads {
    align-items: center;
    margin-bottom: 8px;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    min-width: 0;
  }
  .head.right {
    flex-direction: row-reverse;
  }
  .avatar {
    border-radius: 6px;
    flex: none;
  }
  /* a select dressed as the heading it replaces */
  .name {
    min-width: 0;
    max-width: 100%;
    padding: 2px 4px;
    border: 0;
    border-bottom: 1px dashed var(--muted);
    border-radius: 0;
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: 22px;
    font-weight: 600;
    text-overflow: ellipsis;
    cursor: pointer;
  }
  .head:not(.right) .name {
    text-align: right;
  }
  .name:hover,
  .name:focus-visible {
    border-bottom-color: var(--text);
  }
  .name option {
    background: var(--surface);
    font-size: 14px;
    font-weight: normal;
  }
  .vs {
    text-align: center;
    color: var(--muted);
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .together {
    margin-inline: auto;
    text-align: center;
  }
  .stats {
    align-items: baseline;
  }
  .stats > span {
    padding: 7px 0;
    border-bottom: 1px solid var(--border);
  }
  .stat {
    text-align: center;
    color: var(--text-2);
    font-size: 13px;
  }
  .value {
    text-align: right;
    font-size: 17px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .value.right {
    text-align: left;
  }
  .better {
    color: var(--good);
  }
  .worse {
    color: var(--critical);
  }
  .maps {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 16px;
  }
</style>
