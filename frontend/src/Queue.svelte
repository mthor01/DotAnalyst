<script lang="ts">
  import { get, type QueuePlayer, type QueueStatus } from './lib/api'
  import Chart, { type Ink } from './lib/Chart.svelte'

  let status = $state<QueueStatus | null>(null)
  let error = $state('')

  const load = () =>
    get<QueueStatus>('queue').then(
      (found) => ((status = found), (error = '')),
      (e) => (error = e.message),
    )
  $effect(() => {
    load()
    const timer = setInterval(load, 5000) // a debugging page: it follows the poller while it is open
    return () => clearInterval(timer)
  })

  const span = (s: number) =>
    s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : s < 172800 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} days`
  const ago = (t: number) => `${span(status!.now - t)} ago`
  const date = (t: number) => new Date(t * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  // the downloads step takes every due match, in this order
  const next = (row: QueueStatus['queue'][number]) =>
    row.next_try > status!.now ? `in ${span(row.next_try - status!.now)}` : 'now'
  const STATES = ['pending', 'none', 'parsed', 'unavailable', 'failed']
  const mb = (b: number) => (b / 2 ** 20).toFixed(1)
  const speed = (b: number, s: number) => `${s > 0 ? (b / 2 ** 20 / s).toFixed(2) : '–'} MB/s`

  // in binary units, as the file manager counts them
  const size = (b: number) =>
    b >= 2 ** 30 ? `${(b / 2 ** 30).toFixed(1)} GB` : b >= 2 ** 20 ? `${Math.round(b / 2 ** 20)} MB` : `${Math.round(b / 2 ** 10)} kB`
  // the server lists the parts in a fixed order, so each part keeps its colour whether or not the others are empty
  const SLICE = ['series-1', 'series-2', 'series-3', 'series-4', 'series-5', 'series-6'] as const
  const parts = $derived(status ? status.storage.map((p, i) => ({ ...p, ink: SLICE[i] })) : [])
  const total = $derived(parts.reduce((sum, p) => sum + p.bytes, 0))
  const share = (b: number) => (b === 0 ? '0%' : b / total < 0.01 ? '<1%' : `${Math.round((b / total) * 100)}%`)
  const storageChart = (ink: Ink) => ({
    animation: false, // the page reloads every 5 s; a donut that grows anew each time would never sit still
    tooltip: { trigger: 'item', formatter: (p: { name: string; value: number }) => `${p.name}<br>${size(p.value)}, ${share(p.value)}` },
    series: [
      {
        type: 'pie',
        radius: ['52%', '86%'],
        label: { show: false },
        itemStyle: { borderColor: ink.surface, borderWidth: 2, borderRadius: 4 },
        data: parts.filter((p) => p.bytes > 0).map((p) => ({ name: p.name, value: p.bytes, itemStyle: { color: ink[p.ink] } })),
      },
    ],
  })
</script>

{#snippet person(p: QueuePlayer)}
  <span class="person">
    {#if p.avatar}<img src={p.avatar} alt="" width="20" height="20" />{/if}{p.name ?? p.account_id}
  </span>
{/snippet}

{#if error}
  <p class="error" role="alert">{error}</p>
{/if}
{#if status}
  <h2>Poller</h2>
  <div class="card">
    <table>
      <tbody>
        <tr>
          <th>Now</th>
          <td>{Object.keys(status.running).length ? `${Object.keys(status.running).length} steps at work` : `no step has work; each looks again within ${status.loop_seconds} s`}</td>
        </tr>
        <tr>
          <th>Parser</th>
          <td class={status.parser ? '' : 'error'}>{status.parser ? 'answers on port 5600' : 'does not answer on port 5600: is Docker running?'}</td>
        </tr>
        <tr>
          <th>Downloading</th>
          <td>
            {#each status.downloading as d (d.match_id)}
              <div><a href="#match/{d.match_id}">{d.match_id}</a>: {mb(d.bytes)}{d.total ? ` / ${mb(d.total)}` : ''} MB, {speed(d.bytes, status.now - d.started)}</div>
            {:else}<span class="muted">nothing right now</span>{/each}
          </td>
        </tr>
        <tr>
          <th>Last downloads</th>
          <td>
            {#each status.downloaded as d}
              <div>
                <span class="muted">{ago(d.started + d.seconds)}:</span> <a href="#match/{d.match_id}">{d.match_id}</a>, {mb(d.bytes)} MB in {span(d.seconds)}, {speed(d.bytes, d.seconds)}{#if !d.whole}, <span class="error">cut off{d.total ? ` at ${Math.round((100 * d.bytes) / d.total)}%` : ''}</span>{/if}
              </div>
            {:else}<span class="muted">none since the server started</span>{/each}
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <h2>Steps</h2>
  <p class="muted">
    Each step runs on its own, side by side with the others: it does all the work it finds, then looks again {status.loop_seconds} s later.
  </p>
  <div class="card">
    <table class="steps">
      <thead><tr><th>Step</th><th>Last done</th><th>Planned</th><th>Why some of it waits</th></tr></thead>
      <tbody>
        {#each status.steps as s (s.key)}
          {@const now = status.running[s.key]}
          {@const running = !!now}
          <tr class:running aria-current={running ? 'step' : undefined}>
            <td class="name">{s.name}</td>
            <td>
              {#if now}<strong>running now</strong>, for {span(status.now - now.since)}: {now.doing}{#if now.total} ({now.done} of {now.total}){/if}
              {:else if s.last}<span class="muted">{ago(s.last.at)}:</span> {s.last.what}
              {:else}<span class="muted">not since the server started</span>{/if}
            </td>
            <td>{s.planned}</td>
            <td>
              {#each s.why as reason}<div>{reason}</div>{:else}<span class="muted">nothing</span>{/each}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <h2>Storage <span class="muted">{size(total)}</span></h2>
  <div class="card chart storage">
    <div class="donut">
      <Chart option={storageChart} label="Storage taken by each part of the data folder" height={200} />
    </div>
    <table>
      <thead><tr><th>Part</th><th class="num">Size</th><th class="num">Share</th></tr></thead>
      <tbody>
        {#each parts as p (p.name)}
          <tr>
            <td><span class="swatch" style:background="var(--{p.ink})"></span>{p.name}</td>
            <td class="num">{size(p.bytes)}</td>
            <td class="num muted">{share(p.bytes)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <h2>Replays of stored matches</h2>
  <div class="card">
    <table>
      <thead>
        <tr>{#each STATES as s}<th class="num">{s}</th>{/each}</tr>
      </thead>
      <tbody>
        <tr>{#each STATES as s}<td class="num">{status.states[s] ?? 0}</td>{/each}</tr>
      </tbody>
    </table>
  </div>
  <p class="muted">
    "none" counts every match never tried, also those older than {status.max_age_days} days, which the poller leaves alone.
    "unavailable" is given up: Valve had no file for 14 days, or no longer has it.
  </p>

  <h2>Queue <span class="muted">{status.queue.length}</span></h2>
  <p class="muted">
    The downloads step takes every due one, 4 at a time: never tried first, then newest first. A match without a replay yet
    waits {span(status.retry_seconds)} before its next try.
  </p>
  {#if status.queue.length === 0}
    <p class="muted">Nothing waiting: every replay the poller wants is parsed or given up.</p>
  {:else}
    <div class="card">
      <table>
        <thead>
          <tr><th>Match</th><th>Played</th><th>Whose</th><th>State</th><th>Last tried</th><th>Next try</th><th>Last message</th></tr>
        </thead>
        <tbody>
          {#each status.queue as row (row.match_id)}
            <tr>
              <td><a href="#match/{row.match_id}">{row.match_id}</a></td>
              <td class="muted">{date(row.start_time)}</td>
              <td class="whose">
                {#each row.accounts as p (p.account_id)}{@render person(p)}{/each}
                {#if row.usual.length}
                  <span class="muted">usual game of</span>
                  {#each row.usual as p (p.account_id)}{@render person(p)}{/each}
                {/if}
                {#if row.league}<span class="muted">{row.league}</span>{/if}
              </td>
              <td>{row.state}</td>
              <td class="muted">{row.tried_at ? ago(row.tried_at) : 'never'}</td>
              <td>{next(row)}</td>
              <td class="message">{row.last?.message ?? ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  <h2>Recent events</h2>
  {#if status.events.length === 0}
    <p class="muted">None since the server started. Events are kept in memory only.</p>
  {:else}
    <div class="card">
      <table>
        <thead><tr><th>When</th><th>Match</th><th>What happened</th></tr></thead>
        <tbody>
          {#each status.events as e}
            <tr>
              <td class="muted">{ago(e.at)}</td>
              <td>{#if e.match_id}<a href="#match/{e.match_id}">{e.match_id}</a>{/if}</td>
              <td class="message">{e.message}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
{:else if !error}
  <p class="muted">Loading…</p>
{/if}

<style>
  tbody th {
    width: 160px;
  }
  .message,
  .steps td {
    white-space: normal;
    vertical-align: top;
  }
  .steps .name {
    font-weight: 600;
    width: 200px;
  }
  .steps td:nth-child(3) {
    width: 28%;
  }
  /* the step the poller is in now; the edge is the page's text colour, as the two team colours mean sides */
  .steps tr.running td {
    background: var(--raised);
  }
  .steps tr.running td:first-child {
    box-shadow: inset 3px 0 0 var(--text);
  }
  .storage {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 32px;
  }
  .donut {
    flex: 0 0 200px;
  }
  .storage table {
    flex: 1 1 280px;
    width: auto;
  }
  .whose {
    white-space: normal;
    min-width: 180px;
  }
  .person {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-right: 10px;
    white-space: nowrap;
    vertical-align: top; /* its baseline would be the picture's bottom edge, which lifts the row */
  }
  .person img {
    border-radius: 3px;
  }
</style>
