<script lang="ts">
  import { get, type TeamRow } from './lib/api'

  let rows = $state<TeamRow[]>([])
  let error = $state('')
  let loaded = $state(false)
  let search = $state('')

  get<TeamRow[]>('teams').then(
    (found) => ((rows = found), (loaded = true)),
    (e) => (error = e.message),
  )

  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString('en-GB', { dateStyle: 'medium' })
  const shown = $derived(rows.filter((r) => (r.name ?? '').toLowerCase().includes(search.trim().toLowerCase())))
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if loaded && rows.length === 0}
  <p class="muted">No league games stored yet. They load with the next check for new league games.</p>
{:else}
  <p class="filters">
    <label>Team <input type="search" bind:value={search} placeholder="Name" /></label>
    <span class="muted">{shown.length} of {rows.length} teams of the tracked tournaments</span>
  </p>
  <div class="card tall">
    <table>
      <thead>
        <tr><th>Team</th><th class="num">Games</th><th class="num">Won</th><th>Last played</th></tr>
      </thead>
      <tbody>
        {#each shown as r (r.team_id)}
          <tr>
            <td><a href="#team/{r.team_id}">{r.name || `Team ${r.team_id}`}</a></td>
            <td class="num">{r.games}</td>
            <td class="num">{r.wins}</td>
            <td class="muted">{date(r.last_played)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
