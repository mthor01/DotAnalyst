<script lang="ts">
  import { get, percent, sortedBy, type HeroRow } from './lib/api'
  import Chart, { type Ink } from './lib/Chart.svelte'
  import { heroName } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'

  let { query }: { query: string } = $props()
  let rows = $state<HeroRow[]>([])
  let error = $state('')

  $effect(() => {
    let current = true
    get<HeroRow[]>('heroes', query).then(
      (found) => current && ((rows = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const COLUMNS: [string, (r: HeroRow) => number, (r: HeroRow) => string][] = [
    ['Games', (r) => r.games, (r) => String(r.games)],
    ['Win rate', (r) => r.wins / r.games, (r) => `${percent(r.wins, r.games)}%`],
    ['Kills', (r) => r.kills, (r) => r.kills.toFixed(1)],
    ['Deaths', (r) => r.deaths, (r) => r.deaths.toFixed(1)],
    ['Assists', (r) => r.assists, (r) => r.assists.toFixed(1)],
    ['GPM', (r) => r.gold_per_min, (r) => r.gold_per_min.toFixed(0)],
    ['XPM', (r) => r.xp_per_min, (r) => r.xp_per_min.toFixed(0)],
  ]
  let sort = $state({ column: 0, descending: true })
  const sorted = $derived(sortedBy(rows, COLUMNS[sort.column][1], sort.descending))
  const sortBy = (column: number) =>
    (sort = { column, descending: sort.column === column ? !sort.descending : true })

  // Two measures on different scales get two panels that share the hero order, not two axes on one plot.
  const TOP = 15
  const top = $derived(rows.slice(0, TOP)) // the API returns most played first
  function option(ink: Ink) {
    const axisLabel = { color: ink.muted }
    const splitLine = { lineStyle: { color: ink.grid } }
    const bar = {
      type: 'bar',
      barMaxWidth: 14,
      itemStyle: { color: ink['series-1'], borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: ink['text-2'] },
    }
    const heroes = { type: 'category', inverse: true, data: top.map((r) => heroName(r.hero_id)) }
    const hidden = { axisLabel: { show: false }, axisTick: { show: false }, axisLine: { show: false } }
    return {
      title: [
        { text: 'Games', left: 130, top: 0, textStyle: { color: ink['text-2'], fontSize: 12, fontWeight: 600 } },
        { text: 'Win rate', left: '58%', top: 0, textStyle: { color: ink['text-2'], fontSize: 12, fontWeight: 600 } },
      ],
      grid: [
        { left: 130, width: '36%', top: 28, bottom: 24 },
        { left: '58%', right: 48, top: 28, bottom: 24 },
      ],
      yAxis: [
        { ...heroes, axisLabel: { color: ink.text }, axisTick: { show: false }, axisLine: { lineStyle: { color: ink.axis } } },
        { ...heroes, gridIndex: 1, ...hidden },
      ],
      xAxis: [
        { type: 'value', minInterval: 1, axisLabel, splitLine },
        { type: 'value', gridIndex: 1, min: 0, max: 100, axisLabel: { ...axisLabel, formatter: '{value}%' }, splitLine },
      ],
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: { dataIndex: number }[]) => {
          const r = top[params[0].dataIndex]
          return `<b>${heroName(r.hero_id)}</b><br>${r.games} games · ${r.wins} won, ${r.games - r.wins} lost<br>Win rate ${percent(r.wins, r.games)}%`
        },
      },
      axisPointer: { link: [{ yAxisIndex: 'all' }] },
      series: [
        { ...bar, name: 'Games', data: top.map((r) => r.games) },
        {
          ...bar,
          name: 'Win rate',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: top.map((r) => percent(r.wins, r.games)),
          label: { ...bar.label, formatter: '{c}%' },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: ink.axis, type: 'solid', width: 1 },
            label: { show: false },
            data: [{ xAxis: 50 }],
          },
        },
      ],
    }
  }
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if rows.length === 0}
  <p class="muted">No matches for these filters.</p>
{:else}
  <h2>Most played heroes{rows.length > TOP ? ` (top ${TOP} of ${rows.length})` : ''}</h2>
  <div class="card chart">
    <Chart {option} height={top.length * 26 + 56} label="Games and win rate for the most played heroes; the table below has the same numbers" />
  </div>

  <h2>All heroes</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Hero</th>
          {#each COLUMNS as [title], i}
            <th class="num" aria-sort={sort.column === i ? (sort.descending ? 'descending' : 'ascending') : undefined}>
              <button onclick={() => sortBy(i)}>{title}{sort.column === i ? (sort.descending ? ' ↓' : ' ↑') : ''}</button>
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each sorted as r (r.hero_id)}
          <tr>
            <td><Hero id={r.hero_id} /></td>
            {#each COLUMNS as [, , text]}<td class="num">{text(r)}</td>{/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
