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
  // the mates come most games first; the best win rate counts only mates with enough games for it to say something
  const SURE = 5
  const best = $derived.by(() => {
    const sure = teammates.filter((t) => t.games >= SURE)
    return sure.length > 1 ? sure.reduce((a, b) => (b.wins / b.games > a.wins / a.games ? b : a)).account_id : undefined
  })
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
  <h2 data-block="profile.teammates.mates">With tracked accounts</h2>
  {#if teammates.length === 0}
    <p class="muted" data-block="profile.teammates.mates">No matches on the same team as another tracked account for these filters.</p>
  {/if}
  <!-- one card per mate, most games first, across the page's whole width; a click opens the mate's profile -->
  <ul class="mates" data-block="profile.teammates.mates">
    {#each teammates as t, i (t.account_id)}
      {@const lead = 2 * t.wins - t.games}
      {@const rate = percent(t.wins, t.games)}
      <li>
        <a class="card mate" class:rough={t.games < SURE} href="#account/{t.account_id}" title={t.games < SURE ? `Only ${t.games} ${t.games === 1 ? 'game' : 'games'} together: a rough win rate` : null}>
          <span class="pic">{#if t.avatar}<img src={t.avatar} alt="" width="56" height="56" />{/if}</span>
          <span class="who">
            <b>{t.label ?? t.account_id}</b>
            <span class="muted">{t.games} {t.games === 1 ? 'game' : 'games'} together</span>
            {#if (i === 0 && teammates.length > 1) || t.account_id === best}
              <span class="badges">
                {#if i === 0 && teammates.length > 1}<span class="badge">Most games</span>{/if}
                {#if t.account_id === best}<span class="badge">Best win rate</span>{/if}
              </span>
            {/if}
          </span>
          <span class="rate" class:good={2 * t.wins > t.games} class:bad={2 * t.wins < t.games}>{rate}%</span>
          <span class="split" role="img" aria-label="{t.wins} won, {t.games - t.wins} lost">
            <i class="won" style:width="{(100 * t.wins) / t.games}%"></i><i class="lost"></i>
          </span>
          <span class="tally">
            <span><b class="good">{t.wins} W</b> <b class="bad">{t.games - t.wins} L</b></span>
            <span class:good={lead > 0} class:bad={lead < 0} title="games won minus games lost">{signed(lead)}</span>
          </span>
        </a>
      </li>
    {/each}
    <li class="card adder">
      <button
        class="action"
        onclick={addTeammates}
        disabled={tracking}
        title="Adds every player with {TEAMMATE_GAMES} or more games on their team in their last {TEAMMATE_MATCHES} matches"
      >
        {tracking ? 'Adding…' : '+ Add frequent teammates'}
      </button>
      <span class="muted">Players with {TEAMMATE_GAMES}+ games on the team in the last {TEAMMATE_MATCHES} matches</span>
      <span role="status">{tracked}</span>
    </li>
  </ul>

  <h2 data-block="profile.teammates.heroes">Heroes on my team and against me</h2>
  <div class="filters" data-block="profile.teammates.heroes">
    <span>At least</span>
    <span class="choice" role="group" aria-label="Fewest games of a hero shown">
      {#each MIN_GAMES as n}
        <button aria-pressed={minGames === n} onclick={() => (minGames = n)}>{n}+</button>
      {/each}
    </span>
    <span>games</span>
  </div>
  <div class="sides" data-block="profile.teammates.heroes">
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
  .mates {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 12px;
    margin: 0 0 28px;
    padding: 0;
    list-style: none;
  }
  /* picture and name on top, the win rate big under them, the wins against the losses as one bar */
  .mate {
    display: grid;
    grid-template-columns: 56px minmax(0, 1fr);
    gap: 12px 14px;
    align-items: center;
    height: 100%;
    box-sizing: border-box;
    padding: 16px 18px;
    color: inherit;
    text-decoration: none;
    transition: background-color 0.15s;
  }
  .mate:hover {
    background: var(--raised);
  }
  .pic {
    width: 56px;
    height: 56px;
    border-radius: 6px;
    overflow: hidden;
    background: var(--raised);
  }
  .pic img {
    display: block;
  }
  .who {
    display: grid;
    min-width: 0;
  }
  .who b {
    overflow: hidden;
    font-size: 17px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .who .muted {
    font-size: 13px;
  }
  .rate {
    grid-column: 1 / -1;
    font-size: 34px;
    font-weight: 800;
    font-stretch: var(--wide);
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .split {
    grid-column: 1 / -1;
    display: flex;
    height: 8px;
    border-radius: 4px;
    overflow: hidden;
  }
  .split i {
    display: block;
  }
  .split .won {
    background: var(--good);
  }
  .split .lost {
    flex: 1;
    background: var(--critical);
    opacity: 0.75;
  }
  .tally {
    grid-column: 1 / -1;
    display: flex;
    justify-content: space-between;
    font-size: 14px;
    font-variant-numeric: tabular-nums;
  }
  .badges {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }
  .badge {
    padding: 1px 8px;
    border: 1px solid var(--border);
    border-radius: 10px;
    font-size: 11px;
    color: var(--text-2);
  }
  /* too few games together for the win rate to say much, as the Overview dims its rough numbers */
  .rough {
    opacity: 0.55;
  }
  .rough:hover {
    opacity: 1;
  }
  .adder {
    display: grid;
    align-content: center;
    justify-items: start;
    gap: 8px;
    padding: 16px 18px;
    border: 1px dashed var(--border);
    background: none;
    font-size: 13px;
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
