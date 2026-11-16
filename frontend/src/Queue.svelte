<script lang="ts">
  import { get, type QueueStatus } from './lib/api'

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
  // the poller takes the due matches in this order, per_poll of them a poll
  const next = (row: QueueStatus['queue'][number], i: number) =>
    row.next_try > status!.now ? `in ${span(row.next_try - status!.now)}` : i < status!.per_poll ? 'next poll' : 'a later poll'
  const STATES = ['pending', 'none', 'parsed', 'unavailable', 'failed']
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{/if}
{#if status}
  <h2>Poller</h2>
  <div class="card">
    <table>
      <tbody>
        <tr><th>Now</th><td>{status.doing}, for {span(status.now - status.since)}</td></tr>
        <tr>
          <th>Last poll</th>
          <td>
            {#if !status.last_poll}<span class="muted">none since the server started</span>
            {:else if status.last_poll.error}<span class="error">{ago(status.last_poll.at)}, failed: {status.last_poll.error}</span>
            {:else}{ago(status.last_poll.at)}, took {span(status.last_poll.seconds)}: {status.last_poll.new} new matches, {status.last_poll.parsed} replays parsed{/if}
          </td>
        </tr>
        <tr>
          <th>Next poll</th>
          <td>{status.next_poll ? (status.next_poll > status.now ? `in ${span(status.next_poll - status.now)}` : 'running') : 'after the first'}</td>
        </tr>
        <tr>
          <th>Parser</th>
          <td class={status.parser ? '' : 'error'}>{status.parser ? 'answers on port 5600' : 'does not answer on port 5600: is Docker running?'}</td>
        </tr>
        <tr>
          <th>Replay salts</th>
          <td>
            {status.alt ? 'from the second Steam account, else from OpenDota' : 'from OpenDota only (no STEAM_ALT_USER)'}
            <span class="muted">({status.salts_from_steam} stored from Steam)</span>
          </td>
        </tr>
        <tr>
          <th>Dota client folder</th>
          <td>{status.folder.ready} replays to parse, {status.folder.downloading} still downloading</td>
        </tr>
      </tbody>
    </table>
  </div>

  <h2>Replays of stored matches</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          {#each STATES as s}<th class="num">{s}</th>{/each}
          <th class="num">parsed, stats missing</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          {#each STATES as s}<td class="num">{status.states[s] ?? 0}</td>{/each}
          <td class="num">{status.without_stats}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="muted">
    "none" counts every match never tried, also those older than {status.max_age_days} days, which the poller leaves alone.
    "unavailable" is given up: Valve had no file for 14 days, or no longer has it.
  </p>

  <h2>Queue <span class="muted">{status.queue.length}</span></h2>
  <p class="muted">
    Up to {status.per_poll} a poll: never tried first, then newest first. A match without a replay yet waits
    {span(status.retry_seconds)}; "Check for new games" does not wait.
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
          {#each status.queue as row, i (row.match_id)}
            <tr>
              <td><a href="#match/{row.match_id}">{row.match_id}</a></td>
              <td class="muted">{date(row.start_time)}</td>
              <td>{row.league ? 'league' : 'account'}</td>
              <td>{row.state}</td>
              <td class="muted">{row.tried_at ? ago(row.tried_at) : 'never'}</td>
              <td>{next(row, i)}</td>
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
  .message {
    white-space: normal;
  }
</style>
