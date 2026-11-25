<script lang="ts">
  import { TEAMMATE_GAMES, TEAMMATE_MATCHES, get, percent, post, sortedBy, type Account, type MatchupRow, type TeammateRow } from './lib/api'
  import { heroName, heroPortrait } from './lib/constants.svelte'
  import WinRate from './lib/WinRate.svelte'

  let { query, account, ontracked }: { query: string; account: Account | undefined; ontracked: () => void } = $props()
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

  let tracking = $state(false)
  let tracked = $state('') // what the last "Add frequent teammates" did
  async function addTeammates() {
    tracking = true
    try {
      const { added } = await post<{ added: number[] }>(`accounts/${account?.account_id}/teammates`)
      tracked = `${added.length} added. Their matches load with the next check.`
      if (added.length) ontracked()
    } catch (e) {
      tracked = `Could not add them: ${(e as Error).message}`
    }
    tracking = false
  }

  // each side of the hero tables counts only its own games, and sorts on its own
  type Side = 'with' | 'against'
  const SIDES: [Side, string][] = [['with', 'On my team'], ['against', 'Against me']]
  const MIN_GAMES = [1, 3, 5, 10]
  let minGames = $state(5)
  type Key = 'games' | 'rate'
  let sorts = $state<Record<Side, { key: Key; down: boolean }>>({ with: { key: 'games', down: true }, against: { key: 'games', down: true } })
  const games = (r: MatchupRow, side: Side) => r[`${side}_games`]
  const wins = (r: MatchupRow, side: Side) => r[`${side}_wins`]
  const rows = (side: Side) =>
    sortedBy(
      matchups.filter((r) => games(r, side) >= minGames),
      sorts[side].key === 'games' ? (r) => games(r, side) : (r) => wins(r, side) / games(r, side),
      sorts[side].down,
    )
  const sortBy = (side: Side, key: Key) => (sorts[side] = { key, down: sorts[side].key === key ? !sorts[side].down : true })
  const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${-n}` : '0')
</script>

{#snippet header(side: Side, label: string, key: Key)}
  {@const sort = sorts[side]}
  <th aria-sort={sort.key === key ? (sort.down ? 'descending' : 'ascending') : undefined}>
    <button onclick={() => sortBy(side, key)}>
      {label}<span class="arrow" aria-hidden="true">{sort.key === key ? (sort.down ? '▾' : '▴') : ''}</span>
    </button>
  </th>
{/snippet}

{#if error}
  <p class="error" role="alert">{error}</p>
{:else}
  <h2>With tracked accounts</h2>
  <div class="card friends">
    {#if teammates.length === 0}
      <p>No matches on the same team as another tracked account for these filters.</p>
    {:else}
      <table>
        <thead>
          <tr><th>Account</th><th class="num">Games</th><th>Win rate</th><th class="num">Won − lost</th></tr>
        </thead>
        <tbody>
          {#each teammates as t (t.account_id)}
            {@const lead = 2 * t.wins - t.games}
            <tr>
              <td>
                <a class="who" href="#account/{t.account_id}">
                  <span class="pic">{#if t.avatar}<img src={t.avatar} alt="" width="24" height="24" />{/if}</span>
                  {t.label ?? t.account_id}
                </a>
              </td>
              <td class="num">{t.games}</td>
              <td><WinRate wins={t.wins} games={t.games} /></td>
              <td class="num" class:good={lead > 0} class:bad={lead < 0}>{signed(lead)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    <p class="track">
      <button
        class="action"
        onclick={addTeammates}
        disabled={tracking}
        title="Adds every player with {TEAMMATE_GAMES} or more games on their team in their last {TEAMMATE_MATCHES} matches"
      >
        {tracking ? 'Adding…' : 'Add frequent teammates'}
      </button>
      <span role="status">{tracked}</span>
    </p>
  </div>

  <h2>Heroes on my team and against me</h2>
  <div class="filters">
    <span>At least</span>
    <span class="choice" role="group" aria-label="Fewest games of a hero shown">
      {#each MIN_GAMES as n}
        <button aria-pressed={minGames === n} onclick={() => (minGames = n)}>{n}+</button>
      {/each}
    </span>
    <span>games</span>
  </div>
  <div class="sides">
    {#each SIDES as [side, title]}
      {@const shown = rows(side)}
      <div class="card tall">
        <h3>{title}</h3>
        <table>
          <thead>
            <tr>
              <th>Hero</th>
              {@render header(side, 'Games', 'games')}
              {@render header(side, 'My win rate', 'rate')}
            </tr>
          </thead>
          <tbody>
            {#each shown as r (r.hero_id)}
              <tr>
                <td><img src={heroPortrait(r.hero_id)} alt={heroName(r.hero_id)} title={heroName(r.hero_id)} width="44" height="25" loading="lazy" /></td>
                <td>{games(r, side)}</td>
                <td><WinRate wins={wins(r, side)} games={games(r, side)} /></td>
              </tr>
            {:else}
              <tr><td colspan="3">No hero with {minGames} or more games.</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/each}
  </div>
{/if}

<style>
  .friends {
    width: fit-content;
    max-width: 100%;
  }
  .friends > p {
    margin: 0;
    padding: 10px 12px;
  }
  .friends table + .track {
    border-top: 1px solid var(--grid);
  }
  .track {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 12px;
  }
  .track span {
    color: var(--text-2);
  }
  .who {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .pic {
    width: 24px;
    height: 24px;
    border-radius: 3px;
    overflow: hidden;
    background: var(--raised);
  }
  .pic img {
    display: block;
  }
  .good {
    color: var(--good);
  }
  .bad {
    color: var(--critical);
  }
  .sides {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    gap: 12px;
    align-items: start;
  }
  .sides h3 {
    margin: 0;
    padding: 12px 12px 4px;
  }
  .sides img {
    display: block;
  }
</style>
