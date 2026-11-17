<script lang="ts">
  import { get, percent, sortedBy, type TeamDetail, type TeamHero } from './lib/api'
  import { heroIcon, heroName } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'
  import Openings from './lib/Openings.svelte'
  import RoleWheel from './lib/RoleWheel.svelte'
  import WardHeat from './lib/WardHeat.svelte'

  let { id, query }: { id: string; query: string } = $props()
  let team = $state<TeamDetail>()
  let error = $state('')
  let fetched = $state(0) // goes up when a replay asked for on this page has arrived: the team is read again

  $effect(() => {
    fetched
    let current = true // a slower, older request must not overwrite a newer one
    get<TeamDetail>(`teams/${id}?${query}`).then(
      (found) => current && ((team = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString(undefined, { dateStyle: 'medium' })
  const games = $derived(team?.games.length ?? 0)
  /** A count with its share of the team's games: 5 (17%) */
  const ofGames = (n: number) => (n ? `${n} (${percent(n, games)}%)` : '–')
  const rate = (part: number, whole: number) => (whole ? `${percent(part, whole)}%` : '–')
  // title, the number the column sorts by, and what the cell says. A rate of nothing sorts below every rate
  const COLUMNS: [string, (h: TeamHero) => number, (h: TeamHero) => string][] = [
    ['Games played', (h) => h.picked, (h) => (h.picked ? String(h.picked) : '–')],
    ['Win rate', (h) => (h.picked ? h.wins / h.picked : -1), (h) => rate(h.wins, h.picked)],
    ['Banned against them', (h) => h.banned_against, (h) => ofGames(h.banned_against)],
    ['Picked by enemy team', (h) => h.picked_against, (h) => ofGames(h.picked_against)],
    ['Open', (h) => h.open, (h) => ofGames(h.open)],
    ['Picked when open', (h) => (h.open ? h.picked / h.open : -1), (h) => rate(h.picked, h.open)],
  ]
  let sort = $state({ column: 2, descending: true })
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
  const one = (n: number) => n.toFixed(1)
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
  {#if !games}
    <p class="muted">No league games of theirs in this season and time frame. <a href="#teams">All teams</a></p>
  {:else}
  <p class="muted">{games} league games, {wins} won ({percent(wins, games)}%). {seasons}. <a href="#teams">All teams</a></p>

  <h2>Heroes in their drafts</h2>
  <p class="muted">
    A hero is open in a game when neither side banned it and the enemy team did not pick it. The percentages beside a
    count are of their {games} games; the win rate is of the games they played the hero, and picked when open of the
    games it was open. A hero banned against them often and picked nearly every time it is open is worth a ban.
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
  <p class="muted">
    Everyone who played a league game for them. Click a player for their heroes, with the averages of a game on each,
    and for where they place their wards.
  </p>
  {#each team.players as p (p.account_id)}
    <details class="card player">
      <summary>
        <b>{p.name ?? p.account_id}</b>
        <span class="muted">{p.games} {p.games === 1 ? 'game' : 'games'}</span>
        {@render icons(p.heroes.map((h) => h.hero_id))}
      </summary>
      <div class="profile">
        <table>
          <thead>
            <tr>
              <th>Hero</th><th class="num">Games</th><th class="num">Win rate</th><th class="num">K / D / A</th>
              <th class="num">Last hits</th><th class="num">GPM</th><th class="num">XPM</th>
            </tr>
          </thead>
          <tbody>
            {#each p.heroes as h (h.hero_id)}
              <tr>
                <td><Hero id={h.hero_id} /></td>
                <td class="num">{h.games}</td>
                <td class="num">{rate(h.wins, h.games)}</td>
                <td class="num">{one(h.kills)} / {one(h.deaths)} / {one(h.assists)}</td>
                <td class="num">{Math.round(h.last_hits)}</td>
                <td class="num">{Math.round(h.gold_per_min)}</td>
                <td class="num">{Math.round(h.xp_per_min)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        <section class="wards">
          <h3>Wards placed</h3>
          {#if p.replays || p.usual_replays}
            <WardHeat wards={p.wards} label="Heatmap of the wards {p.name ?? p.account_id} placed" byGame />
            <p class="muted">
              From the {p.replays} of their {p.games} tournament games whose replay is parsed, and {p.usual_replays} of
              their usual matches with a parsed replay.
            </p>
          {:else}
            <p class="muted">
              None of their games has a parsed replay yet, and wards are only in replays. Request the replays under
              "First moves" below, or with the button on a game's page.
            </p>
          {/if}
        </section>
        <section class="outside">
          <h3>Their last {p.outside.length || ''} games outside the league</h3>
          {#if p.outside.length}
            <RoleWheel games={p.outside} none="Lane unknown" />
            <p class="muted">
              From OpenDota's list of their games, without league and lobby games, whatever the filters above. The lane
              is OpenDota's, known only for the games it parsed.
            </p>
          {:else if p.outside_listed}
            <p class="muted">OpenDota lists no games of theirs outside the league; their match history may be private.</p>
          {:else}
            <p class="muted">Not asked for yet. The poller asks OpenDota for five players a minute; Refresh asks for all of them now.</p>
          {/if}
        </section>
      </div>
    </details>
  {/each}

  <h2>First moves</h2>
  <p class="muted">
    Where their five heroes walked from the start of the pre-game to 0:30, in their last six games on one side. One
    colour per game; the button above the map switches between Radiant and Dire, the buttons beside it switch games on and off, the
    slider moves the clock.
  </p>
  <Openings games={team.games} onfetched={() => (fetched += 1)} />

  <h2>Games</h2>
  <p class="muted">The date opens the game like any match. One without a replay has a button there that requests it.</p>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Season</th>
          <th>Against</th>
          <th>Result</th>
          <th>Their picks</th>
          <th>Enemy picks</th>
          <th>Banned against them</th>
          <th>Banned by them</th>
          <th>Replay</th>
        </tr>
      </thead>
      <tbody>
        {#each team.games as g (g.match_id)}
          <tr>
            <td><a href="#match/{g.match_id}">{date(g.start_time)}</a></td>
            <td class="muted">{g.league}</td>
            <td>
              {#if g.opponent_id}
                <a href="#team/{g.opponent_id}">{g.opponent || `Team ${g.opponent_id}`}</a>
              {:else}
                <span class="muted">No team</span>
              {/if}
            </td>
            <td><span class="dot {g.win ? 'won' : 'lost'}"></span>{g.win ? 'Won' : 'Lost'}</td>
            <td>{@render icons(g.picks)}</td>
            <td>{@render icons(g.picks_against)}</td>
            <td>{@render icons(g.bans_against)}</td>
            <td>{@render icons(g.bans)}</td>
            <td class="muted">{g.replay ? 'Parsed' : '–'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {/if}
{/if}

<style>
  .icons {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
  }
  td .icons {
    flex-wrap: nowrap; /* a game's five picks read as one row */
  }
  .player {
    margin-bottom: 6px;
  }
  summary {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 14px;
    padding: 8px 12px;
    cursor: pointer;
  }
  summary b {
    min-width: 16ch;
  }
  summary .muted {
    min-width: 9ch;
  }
  .profile {
    display: grid;
    grid-template-columns: minmax(420px, 1fr) minmax(280px, 520px);
    grid-template-rows: auto 1fr; /* the tall ward map takes the spare height, so the wheel sits right under the table */
    gap: 12px 24px;
    align-items: start;
    padding: 4px 12px 14px;
  }
  .wards {
    grid-row: span 2;
  }
  @media (max-width: 1000px) {
    .profile {
      grid-template-columns: 1fr;
      grid-template-rows: none;
    }
    .wards {
      grid-row: auto;
    }
  }
  .profile h3 {
    margin: 6px 0 8px;
    font-size: 15px;
  }
</style>
