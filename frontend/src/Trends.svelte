<script lang="ts">
  import { METRICS, get, queryFor, type Account, type MetricPoint } from './lib/api'
  import Chart, { type Ink } from './lib/Chart.svelte'

  let { query, accounts }: { query: string; accounts: Account[] } = $props()

  const WINDOW = 20
  // shortcut: five series colours, so a sixth account would repeat the first one's; cap or facet when there are more
  const COLORS = 5
  let metric = $state(METRICS[0])
  let shown = $state<number[]>([])
  let points = $state<Record<number, MetricPoint[]>>({})
  let error = $state('')

  $effect(() => {
    shown = accounts.slice(0, COLORS).map((a) => a.account_id)
  })
  $effect(() => {
    let current = true
    Promise.all(accounts.map((a) => get<MetricPoint[]>('metrics', queryFor(query, a.account_id, { metric: metric.name })))).then(
      (found) => current && ((points = Object.fromEntries(accounts.map((a, i) => [a.account_id, found[i]]))), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const label = (a: Account) => a.label ?? String(a.account_id)
  const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / values.length
  /** [time, average of this match and up to WINDOW - 1 before it] */
  function rolling(matches: MetricPoint[]): [number, number][] {
    return matches.map((m, i) => [m.start_time * 1000, mean(matches.slice(Math.max(0, i + 1 - WINDOW), i + 1).map((p) => p.value))])
  }
  const lines = $derived(
    accounts
      .map((account, i) => ({ account, color: `series-${(i % COLORS) + 1}` as keyof Ink, matches: points[account.account_id] ?? [] }))
      .filter((line) => shown.includes(line.account.account_id) && line.matches.length),
  )

  function option(ink: Ink) {
    const date = (ms: number) => new Date(ms).toLocaleDateString(undefined, { dateStyle: 'medium' })
    return {
      grid: { left: 64, right: 110, top: 16, bottom: 28 },
      xAxis: {
        type: 'time',
        axisLabel: { color: ink.muted },
        axisLine: { lineStyle: { color: ink.axis } },
        splitLine: { show: false },
      },
      // a rolling average is read for its change, so the axis follows the data and does not start at zero
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: ink.muted, formatter: (v: number) => metric.show(v) },
        splitLine: { lineStyle: { color: ink.grid } },
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: { marker: string; seriesName: string; value: [number, number] }[]) =>
          params
            .map((p) => `${p.marker}${p.seriesName}, ${date(p.value[0])} <b style="float:right;margin-left:16px">${metric.show(p.value[1])}</b>`)
            .join('<br>'),
      },
      series: lines.map((line) => ({
        type: 'line',
        name: label(line.account),
        data: rolling(line.matches),
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: ink[line.color] },
        endLabel: { show: true, formatter: '{a}', color: ink['text-2'], distance: 6 },
        labelLayout: { moveOverlap: 'shiftY' },
        emphasis: { focus: 'series' },
      })),
    }
  }
</script>

<div class="filters">
  <label>
    Metric
    <select bind:value={metric}>
      {#each METRICS as m}<option value={m}>{m.label}</option>{/each}
    </select>
  </label>
  {#each accounts as a, i}
    <label>
      <input type="checkbox" bind:group={shown} value={a.account_id} />
      <i class="swatch" style:background="var(--series-{(i % COLORS) + 1})"></i>{label(a)}
    </label>
  {/each}
</div>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if lines.length === 0}
  <p class="muted">No parsed replays with this metric for these accounts and filters.</p>
{:else}
  <p class="muted">Each point is the average of that match and up to {WINDOW - 1} parsed matches before it, so a line's first stretch rests on few matches. Set From above to zoom into a period.</p>
  <div class="card chart">
    <Chart {option} height={360} label="{metric.label}: rolling average over the last {WINDOW} parsed matches, one line per account; the table below has the averages" />
  </div>

  <div class="card">
    <table>
      <thead>
        <tr><th>Account</th><th class="num">Parsed matches</th><th class="num">Average</th><th class="num">Last {WINDOW}</th></tr>
      </thead>
      <tbody>
        {#each lines as line (line.account.account_id)}
          {@const values = line.matches.map((m) => m.value)}
          <tr>
            <td>{label(line.account)}</td>
            <td class="num">{values.length}</td>
            <td class="num">{metric.show(mean(values))}</td>
            <td class="num">{metric.show(mean(values.slice(-WINDOW)))}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .chart {
    margin-bottom: 16px;
  }
  .swatch {
    margin-left: 2px;
  }
</style>
