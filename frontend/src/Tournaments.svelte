<script lang="ts">
  import { get, post, type TournamentRow } from './lib/api'
  import { loadConstants } from './lib/constants.svelte'
  import Teams from './Teams.svelte'

  let { tab }: { tab: string } = $props()
  let rows = $state<TournamentRow[]>([])
  let error = $state('')
  let leagueId = $state('')
  let adding = $state(false)
  let added = $state('') // what the last add did, or why it failed

  const load = () => get<TournamentRow[]>('leagues').then((found) => (rows = found), (e) => (error = e.message))
  load()

  async function add(event: SubmitEvent) {
    event.preventDefault()
    adding = true
    try {
      // sent as text: the server reads it as a number, without JavaScript rounding a long id
      const found = await post<{ name: string }>('leagues', { league_id: leagueId })
      added = `${found.name} is tracked. Its games load with the next check.`
      leagueId = ''
      await Promise.all([load(), loadConstants()]) // loadConstants for the header's Tournament filter
    } catch (e) {
      added = `Could not add it: ${(e as Error).message}`
    }
    adding = false
  }

  const date = (seconds: number | null) =>
    seconds === null ? '' : new Date(seconds * 1000).toLocaleDateString(undefined, { dateStyle: 'medium' })
</script>

<div class="choice tabs" role="group" aria-label="Part of the tournaments page">
  <button aria-pressed={tab !== 'teams'} onclick={() => (location.hash = 'tournaments')}>Tournaments</button>
  <button aria-pressed={tab === 'teams'} onclick={() => (location.hash = 'tournaments/teams')}>Teams</button>
</div>

{#if tab === 'teams'}
  <Teams />
{:else if error}
  <p class="error" role="alert">{error}</p>
{:else}
  <form class="filters" onsubmit={add}>
    <label>
      League id
      <input bind:value={leagueId} required pattern="\d+" inputmode="numeric" placeholder="league id" />
    </label>
    <button class="action" disabled={adding}>{adding ? 'Adding…' : 'Add tournament'}</button>
    <span class="muted" role="status">{added}</span>
  </form>
  <div class="card">
    <table>
      <thead>
        <tr><th>Tournament</th><th class="num">Games</th><th class="num">Teams</th><th>First game</th><th>Last game</th></tr>
      </thead>
      <tbody>
        {#each rows as r (r.league_id)}
          <tr>
            <td>{r.name} <span class="muted">{r.league_id}</span></td>
            <td class="num">{r.games}</td>
            <td class="num">{r.teams}</td>
            <td class="muted">{date(r.first_game)}</td>
            <td class="muted">{date(r.last_game)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .tabs {
    margin: 4px 0 14px;
  }
  .filters {
    margin: 0 0 14px;
  }
  input {
    width: 9em;
  }
</style>
