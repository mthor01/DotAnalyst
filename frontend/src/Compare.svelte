<script module lang="ts">
  import { METRICS, clock, type MatchRow, type MetricAverage, type WardSpot } from './lib/api'

  export type Side = { matches: MatchRow[]; wards: WardSpot[]; averages: Record<string, MetricAverage> }
  const mean = (rows: MatchRow[], value: (r: MatchRow) => number) =>
    rows.length ? rows.reduce((sum, r) => sum + value(r), 0) / rows.length : undefined
  const fixed = (digits: number) => (v: number) => v.toFixed(digits)
  /** The rows of the comparison: `lower` when less is better, `count` when neither is (only how much was seen);
   *  `heroes` is the row of most played heroes, pictures rather than a number */
  export type Row = { label: string; of: (s: Side) => number | undefined; show: (v: number) => string; lower?: boolean; count?: boolean; heroes?: true; title?: (s: Side) => string }
  /** A replay stat, averaged over the account's parsed matches */
  const metric = (name: string, more: Partial<Row> = {}): Row => {
    const m = METRICS.find((m) => m.name === name)!
    return { label: m.label, of: (s) => s.averages[name]?.average, show: m.show, title: (s) => `${s.averages[name]?.matches ?? 0} parsed matches`, ...more }
  }
  export const GROUPS: [string, Row[]][] = [
    ['General', [
      { label: 'Matches', of: (s) => s.matches.length, show: String, count: true },
      // every parsed match of an account has a kill participation, so its count is the number of parsed matches
      { label: 'Parsed matches', of: (s) => s.averages.kill_participation?.matches ?? 0, show: String, count: true },
      { label: 'Most played heroes', of: () => undefined, show: String, count: true, heroes: true },
      { label: 'Win rate', of: (s) => mean(s.matches, (r) => r.win), show: (v) => `${Math.round(100 * v)}%` },
      { label: 'Kills', of: (s) => mean(s.matches, (r) => r.kills), show: fixed(1) },
      { label: 'Deaths', of: (s) => mean(s.matches, (r) => r.deaths), show: fixed(1), lower: true },
      { label: 'Assists', of: (s) => mean(s.matches, (r) => r.assists), show: fixed(1) },
    ]],
    ['Economy', [
      { label: 'Gold per minute', of: (s) => mean(s.matches, (r) => r.gold_per_min), show: fixed(0) },
      { label: 'Experience per minute', of: (s) => mean(s.matches, (r) => r.xp_per_min), show: fixed(0) },
      metric('camps_stacked'),
    ]],
    ['Lane', [metric('lane_cs_diff'), metric('lane_nw_diff'), metric('lane_dn_diff')]],
    ['Fights', [metric('kill_participation'), metric('fight_participation'), metric('deaths_outside_fights', { lower: true })]],
    ['Wards', [
      metric('obs_placed'), metric('sen_placed'), metric('obs_bought'), metric('sen_bought'), metric('wards_destroyed'),
      metric('obs_lifetime', { show: (v) => clock(Math.round(v)) }),
    ]],
  ] // prettier-ignore
  const TOP_HEROES = 5
</script>

<script lang="ts">
  import About from './lib/About.svelte'
  import { untrack } from 'svelte'
  import { get, percent, queryFor, type Account, type TeammateRow } from './lib/api'
  import { heroIcon, heroName } from './lib/constants.svelte'
  import { tally } from './lib/RoleWheel.svelte'
  import WardHeat, { HOW } from './lib/WardHeat.svelte'

  let { query, accounts }: { query: string; accounts: Account[] } = $props()
  // the two accounts compared, the first two tracked ones at first
  let chosen = $state(untrack(() => [accounts[0]?.account_id, accounts[1]?.account_id ?? accounts[0]?.account_id]))
  let together = $state<TeammateRow | undefined>()
  let sides = $state.raw<Side[]>([])
  let error = $state('')
  // what both ward maps show, so that every button, dropdown, slider and zoom moves the two together
  let maps = $state({ periods: [true, true, true, true, true], share: 0, chosen: [] as string[], moved: null })

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
        {#each GROUPS as [title, rows] (title)}
          <h3 class="group">{title}</h3>
          {#each rows as row (row.label)}
            {#each [0, 1] as i}
              {#if row.heroes}
                <!-- the most played next to the label in the middle, on both sides -->
                <span class="value heroes" class:right={i === 1}>
                  {#each tally(sides[i].matches).slice(0, TOP_HEROES) as h (h.hero_id)}
                    {@const note = `${heroName(h.hero_id)}: ${h.games} ${h.games === 1 ? 'match' : 'matches'}, ${percent(h.wins, h.games)}% won`}
                    <img src={heroIcon(h.hero_id)} alt={note} title={note} width="30" height="30" />
                  {:else}–{/each}
                </span>
              {:else}
                {@const v = row.of(sides[i])}
                <span class="value {verdict(row, i)}" class:right={i === 1} title={row.title?.(sides[i])}>{v === undefined ? '–' : row.show(v)}</span>
              {/if}
              {#if i === 0}<span class="stat">{row.label}</span>{/if}
            {/each}
          {/each}
        {/each}
      </div>
      <p class="muted">Green is the better of the two, red the worse.<About>Green is the better of the two, red the worse. The replay numbers average each account's matches with a parsed replay, the rest every match the filters keep; the games together count every stored match.</About></p>

      <h2>Wards</h2>
      <div class="maps">
        <!-- one box between the maps holds every control; the maps only show, and zoom together -->
        {#each ['map', 'controls', 'map'] as const as only, k}
          {@const i = k ? 1 : 0}
          {@const a = account(chosen[i])}
          <div class={only === 'controls' ? 'filterbox controls' : 'card map'}>
            <WardHeat
              {only}
              wards={only === 'map' ? sides[i].wards : []}
              games={only === 'map' ? sides[i].matches.filter((r) => r.replay_state === 'parsed') : []}
              label={`${a?.label ?? chosen[i]}'s wards`}
              bind:periods={maps.periods}
              bind:share={maps.share}
              bind:chosen={maps.chosen}
              bind:moved={maps.moved}
            />
          </div>
        {/each}
      </div>
      <p class="muted">Left the first player's wards, right the second's.<About>Left the first player's wards, right the second's; the box in the middle and a zoom on either map apply to both. {HOW}</About></p>
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
  /* a heading across all three columns; the first sits at the card's top */
  .group {
    grid-column: 1 / -1;
    margin: 18px 0 2px;
    text-align: center;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-2);
  }
  .group:first-child {
    margin-top: 8px;
  }
  .heroes {
    display: flex;
    flex-direction: row-reverse;
    gap: 4px;
    align-self: center;
  }
  .heroes.right {
    flex-direction: row;
  }
  .heroes img {
    display: block;
    border-radius: 3px;
  }
  .better {
    color: var(--good);
  }
  .worse {
    color: var(--critical);
  }
  .maps {
    display: grid;
    grid-template-columns: minmax(0, 520px) 360px minmax(0, 520px); /* 520: as wide as a map gets */
    justify-content: center;
    align-items: start;
    gap: 16px;
  }
  /* too narrow for three columns: the panel on top, the maps below it */
  @media (max-width: 1200px) {
    .maps {
      grid-template-columns: 1fr;
    }
    .controls {
      order: -1;
    }
  }
</style>
