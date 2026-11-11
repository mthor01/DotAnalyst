<script lang="ts">
  import { get, percent, sortedBy, type MatchupRow, type TeammateRow } from './lib/api'
  import Hero from './lib/Hero.svelte'

  let { query }: { query: string } = $props()
  let teammates = $state<TeammateRow[]>([])
  let matchups = $state<MatchupRow[]>([])
  let error = $state('')

  $effect(() => {
    let current = true
    Promise.all([get<TeammateRow[]>('teammates', query), get<MatchupRow[]>('matchups', query)]).then(
      ([t, m]) => current && ((teammates = t), (matchups = m), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  // a win rate over a handful of games says little, so those sort below every real one
  const rate = (wins: number, games: number) => (games ? wins / games : -1)
  const COLUMNS: [string, (r: MatchupRow) => number, (r: MatchupRow) => string][] = [
    ['Games with', (r) => r.with_games, (r) => String(r.with_games)],
    ['Win rate with', (r) => rate(r.with_wins, r.with_games), (r) => (r.with_games ? `${percent(r.with_wins, r.with_games)}%` : '–')],
    ['Games against', (r) => r.against_games, (r) => String(r.against_games)],
    ['Win rate against', (r) => rate(r.against_wins, r.against_games), (r) => (r.against_games ? `${percent(r.against_wins, r.against_games)}%` : '–')],
  ]
  let minGames = $state(5)
  let sort = $state({ column: 0, descending: true })
  const shown = $derived(
    sortedBy(
      matchups.filter((r) => r.with_games + r.against_games >= minGames),
      COLUMNS[sort.column][1],
      sort.descending,
    ),
  )
  const sortBy = (column: number) =>
    (sort = { column, descending: sort.column === column ? !sort.descending : true })
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else}
  <h2>With tracked accounts</h2>
  {#if teammates.length === 0}
    <p class="muted">No matches on the same team as another tracked account for these filters.</p>
  {:else}
    <div class="card">
      <table>
        <thead>
          <tr><th>Account</th><th class="num">Games together</th><th class="num">Won</th><th class="num">Win rate</th></tr>
        </thead>
        <tbody>
          {#each teammates as t (t.account_id)}
            <tr>
              <td>{t.label ?? t.account_id}</td>
              <td class="num">{t.games}</td>
              <td class="num">{t.wins}</td>
              <td class="num">{percent(t.wins, t.games)}%</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  <h2>Heroes on my team and against me</h2>
  <p class="filters">
    <label>At least <input type="number" min="1" bind:value={minGames} style="width: 4em" /> games in total</label>
    <span class="muted">{shown.length} of {matchups.length} heroes · win rates are always mine</span>
  </p>
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
        {#each shown as r (r.hero_id)}
          <tr>
            <td><Hero id={r.hero_id} /></td>
            {#each COLUMNS as [, , text]}<td class="num">{text(r)}</td>{/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
