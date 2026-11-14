<script lang="ts">
  import { get, sortedBy, type TeamDetail, type TeamHero } from './lib/api'
  import { heroIcon, heroName } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'

  let { id }: { id: string } = $props()
  let team = $state<TeamDetail>()
  let error = $state('')

  $effect(() => {
    let current = true // a slower, older request must not overwrite a newer one
    get<TeamDetail>(`teams/${id}`).then(
      (found) => current && ((team = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString(undefined, { dateStyle: 'medium' })
  const some = (n: number) => (n ? String(n) : '–')
  // counts, not percentages: with a handful of games "3 of 4" says how little there is to go on
  const COLUMNS: [string, (h: TeamHero) => number, (h: TeamHero) => string][] = [
    ['Banned against them', (h) => h.banned_against, (h) => some(h.banned_against)],
    ['Banned by them', (h) => h.banned, (h) => some(h.banned)],
    ['Open', (h) => h.open, (h) => String(h.open)],
    ['Picked when open', (h) => h.picked, (h) => (h.open ? `${h.picked} of ${h.open}` : '–')],
    ['Won with it', (h) => h.wins, (h) => (h.picked ? `${h.wins} of ${h.picked}` : '–')],
  ]
  let sort = $state({ column: 0, descending: true })
  const TOP = 15 // the rest are mostly heroes seen once; the players and games below matter more
  let all = $state(false)
  const sorted = $derived(sortedBy(team?.heroes ?? [], COLUMNS[sort.column][1], sort.descending))
  const heroes = $derived(all ? sorted : sorted.slice(0, TOP))
  const sortBy = (column: number) =>
    (sort = { column, descending: sort.column === column ? !sort.descending : true })

  const wins = $derived(team?.games.filter((g) => g.win).length ?? 0)
  // "Season 8: 4 games, Season 6: 18 games", newest season first like the games
  const seasons = $derived.by(() => {
    const games: Record<string, number> = {}
    for (const g of team?.games ?? []) games[g.league] = (games[g.league] ?? 0) + 1
    return Object.entries(games).map(([league, n]) => `${league}: ${n} games`).join(', ')
  })
</script>

{#snippet icons(ids: number[])}
  <span class="icons">
    {#each ids as hero}
      {#if heroIcon(hero)}
        <img src={heroIcon(hero)} alt={heroName(hero)} title={heroName(hero)} width="24" height="24" loading="lazy" />
      {:else}
        {heroName(hero)}
      {/if}
    {:else}
      <span class="muted">–</span>
    {/each}
  </span>
{/snippet}

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if team}
  <h2>{team.name || `Team ${team.team_id}`}</h2>
  <p class="muted">{team.games.length} league games, {wins} won. {seasons}. <a href="#teams">All teams</a></p>

  <h2>Heroes in their drafts</h2>
  <p class="muted">
    A hero is open in a game when neither side banned it. A hero banned against them often and picked nearly every
    time it is open is worth a ban; one they leave alone when it is open is not.
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
        {#each heroes as h (h.hero_id)}
          <tr>
            <td><Hero id={h.hero_id} /></td>
            {#each COLUMNS as [, , text]}<td class="num">{text(h)}</td>{/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if sorted.length > TOP}
    <p>
      <button class="action" onclick={() => (all = !all)}>
        {all ? `Show the first ${TOP} heroes` : `Show all ${sorted.length} heroes`}
      </button>
    </p>
  {/if}

  <h2>Players</h2>
  <p class="muted">Everyone who played a league game for them, with games per hero. Hover a hero for its wins.</p>
  <div class="card">
    <table>
      <thead>
        <tr><th>Player</th><th class="num">Games</th><th>Heroes</th></tr>
      </thead>
      <tbody>
        {#each team.players as p (p.account_id)}
          <tr>
            <td>{p.name ?? p.account_id}</td>
            <td class="num">{p.games}</td>
            <td>
              <span class="played">
                {#each p.heroes as h (h.hero_id)}
                  <span title="{heroName(h.hero_id)}: {h.games} games, {h.wins} won">
                    {#if heroIcon(h.hero_id)}
                      <img src={heroIcon(h.hero_id)} alt={heroName(h.hero_id)} width="24" height="24" loading="lazy" />
                    {:else}
                      {heroName(h.hero_id)}
                    {/if}
                    {h.games}
                  </span>
                {/each}
              </span>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <h2>Games</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Season</th>
          <th>Against</th>
          <th>Side</th>
          <th>Result</th>
          <th>Their picks</th>
          <th>Banned against them</th>
          <th>Banned by them</th>
        </tr>
      </thead>
      <tbody>
        {#each team.games as g (g.match_id)}
          <tr>
            <td>{date(g.start_time)}</td>
            <td class="muted">{g.league}</td>
            <td>
              {#if g.opponent_id}
                <a href="#team/{g.opponent_id}">{g.opponent || `Team ${g.opponent_id}`}</a>
              {:else}
                <span class="muted">No team</span>
              {/if}
            </td>
            <td><span class="swatch {g.radiant ? 'radiant' : 'dire'}"></span>{g.radiant ? 'Radiant' : 'Dire'}</td>
            <td><span class="dot {g.win ? 'won' : 'lost'}"></span>{g.win ? 'Won' : 'Lost'}</td>
            <td>{@render icons(g.picks)}</td>
            <td>{@render icons(g.bans_against)}</td>
            <td>{@render icons(g.bans)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .icons,
  .played {
    display: flex;
    gap: 3px;
  }
  .played {
    flex-wrap: wrap;
    gap: 4px 12px;
    color: var(--text-2);
  }
  .played span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
</style>
