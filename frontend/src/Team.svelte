<script lang="ts">
  import { clock, get, percent, sortedBy, type TeamDetail, type TeamHero } from './lib/api'
  import { heroIcon, heroName } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'
  import Openings from './lib/Openings.svelte'
  import RoleWheel from './lib/RoleWheel.svelte'
  import WardHeat from './lib/WardHeat.svelte'
  import Match from './Match.svelte'

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
    ['Banned by them', (h) => h.banned, (h) => ofGames(h.banned)],
    ['Games played', (h) => h.picked, (h) => (h.picked ? String(h.picked) : '–')],
    ['Win rate', (h) => (h.picked ? h.wins / h.picked : -1), (h) => rate(h.wins, h.picked)],
    ['Banned against them', (h) => h.banned_against, (h) => ofGames(h.banned_against)],
    ['Picked by enemy team', (h) => h.picked_against, (h) => ofGames(h.picked_against)],
    ['Open', (h) => h.open, (h) => ofGames(h.open)],
    ['Picked when open', (h) => (h.open ? h.picked / h.open : -1), (h) => rate(h.picked, h.open)],
  ]
  let sort = $state({ column: 3, descending: true }) // banned against them
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
  /** An average net worth lead from their side: +1234, -560, or – with none to average */
  const lead = (n: number | null) => (n === null ? '–' : `${n > 0 ? '+' : ''}${Math.round(n)}`)
  const TABS = ['Games', 'Players', 'Draft', 'General'] as const
  let tab = $state<(typeof TABS)[number]>('Games')
  let unfolded = $state<number[]>([]) // the games whose row is open
  const unfold = (id: number) => (unfolded = unfolded.includes(id) ? unfolded.filter((o) => o !== id) : [...unfolded, id])
  /** The parsed games where first blood is known */
  const bloods = $derived(team?.games.filter((g) => g.first_blood !== null) ?? [])
  const drew = $derived(bloods.filter((g) => g.first_blood).length)
  const LANE_NAMES = { safe: 'Safe lane', mid: 'Mid', off: 'Off lane' } as const
  /** One scale for the three lane bars: the largest mean net worth lead, at least 1000 */
  const laneBound = $derived(Math.max(1000, ...Object.values(team?.lanes ?? {}).map((l) => Math.abs(l.net_worth ?? 0))))
  /** The wards of all their players in the team's own games, for the General tab's map */
  const teamWards = $derived(team?.players.flatMap((p) => p.wards.filter((w) => w.league)) ?? [])
  const parsed = $derived(team?.games.filter((g) => g.replay).map((g) => ({ radiant: g.radiant, win: g.win })) ?? [])
  const PICKS = ['1st pick (first phase)', '2nd pick (second phase)', '3rd pick (second phase)', '4th pick (second phase)', '5th pick (last phase)']
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
  <h2 class="name">
    {#if team.logo}<img src={team.logo} alt="" width="40" height="40" />{/if}
    {team.name || `Team ${team.team_id}`}
  </h2>
  {#if !games}
    <p class="muted">No league games of theirs in this season and time frame. <a href="#teams">All teams</a></p>
  {:else}
  <p class="muted">{games} league games, {wins} won ({percent(wins, games)}%). {seasons}. <a href="#teams">All teams</a></p>

  <div class="choice tabs" role="group" aria-label="Part of the team page">
    {#each TABS as name}
      <button aria-pressed={tab === name} onclick={() => (tab = name)}>{name}</button>
    {/each}
  </div>

  {#if tab === 'General'}
  <div class="pair">
    <section>
      <h2>Wards placed</h2>
      {#if parsed.length}
        <p class="muted">
          Every ward their players placed in the {parsed.length} of their {games} games whose replay is parsed; their
          usual matches are on each player's own map under Players.
        </p>
        <WardHeat wards={teamWards} games={parsed} label="Heatmap of the wards the team placed in its tournament games" />
      {:else}
        <p class="muted">None of their games has a parsed replay yet, and wards are only in replays. Request the replays under "First moves".</p>
      {/if}
    </section>
    <section>
      <h2>First moves</h2>
      <p class="muted">
        Where their five heroes walked from the start of the pre-game to 0:30, in their last six games on one side. One
        colour per game; the button above the map switches between Radiant and Dire, the buttons beside it switch games on
        and off, the slider moves the clock.
      </p>
      <Openings games={team.games} onfetched={() => (fetched += 1)} />
    </section>
  </div>

  <h2>First blood</h2>
  {#if bloods.length}
    <p>They drew first blood in {drew} of the {bloods.length} games whose replay is parsed ({percent(drew, bloods.length)}%).</p>
  {:else}
    <p class="muted">Not known: none of their games has a parsed replay.</p>
  {/if}

  <h2>Lanes at 10:00</h2>
  <p class="muted">
    Their heroes in each lane against the enemy's there, at 10:00 of the parsed games where both sides had a hero in it.
    The lead is theirs minus the enemy's, averaged over those games; the bar grows to the side ahead in net worth.
  </p>
  <div class="lanes">
    {#each Object.entries(LANE_NAMES) as [key, title] (key)}
      {@const l = team.lanes[key as keyof typeof LANE_NAMES]}
      <section class="card lane">
        <h3>{title}</h3>
        <div class="versus">
          <span>Them</span>
          <span class="tug" aria-hidden="true">
            <span><i class="won" style:width="{(100 * Math.max(l.net_worth ?? 0, 0)) / laneBound}%"></i></span>
            <span><i class="lost" style:width="{(100 * Math.max(-(l.net_worth ?? 0), 0)) / laneBound}%"></i></span>
          </span>
          <span>Enemy</span>
        </div>
        {#if l.games}
          <p class="standing">
            {lead(l.net_worth)} net worth, {lead(l.xp)} experience; ahead in {l.ahead} of {l.games} games ({percent(l.ahead, l.games)}%)
          </p>
        {:else}
          <p class="standing muted">No parsed game with both sides in this lane.</p>
        {/if}
      </section>
    {/each}
  </div>

  <h2>First Tormentor</h2>
  <p class="muted">
    The first Tormentor of each of the {team.tormentors.games} games whose replay is parsed, by who took it. Time, heroes
    dead and lead are averages over those games: the dead are the other side's, the lead is the taker's net worth minus
    the other side's.
  </p>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Taken by</th><th class="num">Games</th><th class="num">Time</th>
          <th class="num">Heroes of the other side dead</th><th class="num">Taker's net worth lead</th>
        </tr>
      </thead>
      <tbody>
        {#each [{ title: 'Them', t: team.tormentors.them }, { title: 'The enemy', t: team.tormentors.enemy }] as { title, t }}
          <tr>
            <td>{title}</td>
            <td class="num">{t.count} ({percent(t.count, team.tormentors.them.count + team.tormentors.enemy.count)}%)</td>
            <td class="num">{t.time === null ? '–' : clock(Math.round(t.time))}</td>
            <td class="num">{t.enemies_dead === null ? '–' : one(t.enemies_dead)}</td>
            <td class="num">{lead(t.lead)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <h2>Wisdom runes</h2>
  <p class="muted">
    Every wisdom rune of their parsed games, from 7:00 on. They contested one when at least one of their heroes came within
    ten cells of it between 20 seconds before it appeared and its pickup; heroes and the net worth lead are averages over
    the ones they contested.
  </p>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th></th><th class="num">Runes</th><th class="num">Contested</th><th class="num">Heroes they brought</th>
          <th class="num">Taken by them</th><th class="num">Net worth lead when contested</th>
        </tr>
      </thead>
      <tbody>
        {#each [{ title: 'In their half', w: team.wisdom.own }, { title: 'In the enemy half', w: team.wisdom.enemy }] as { title, w }}
          <tr>
            <td>{title}</td>
            <td class="num">{w.spawns}</td>
            <td class="num">{w.contested} ({percent(w.contested, w.spawns)}%)</td>
            <td class="num">{w.heroes === null ? '–' : one(w.heroes)}</td>
            <td class="num">{w.taken} ({percent(w.taken, w.spawns)}%)</td>
            <td class="num">{lead(w.lead)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  {:else if tab === 'Draft'}
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

  <h2>Roles in their draft</h2>
  <p class="muted">
    Which position the hero of each of their picks went on to play, in the {team.draft[0].reduce((a, b) => a + b, 0)} of
    their games whose replay is parsed. In Captains Mode a team picks once in the first phase, three times in the second
    and once in the last. The percentages are of the row.
  </p>
  <div class="card">
    <table class="draft">
      <thead>
        <tr><th>Pick</th>{#each [1, 2, 3, 4, 5] as p}<th class="num">Position {p}</th>{/each}</tr>
      </thead>
      <tbody>
        {#each team.draft as row, k}
          {@const total = row.reduce((a, b) => a + b, 0)}
          <tr>
            <td>{PICKS[k]}</td>
            {#each row as n}
              <td class="num" style:--share="{percent(n, total)}%">{n ? `${n} (${percent(n, total)}%)` : '–'}</td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {:else if tab === 'Games'}
  <h2>Games</h2>
  <p class="muted">
    The arrow unfolds a game: its draft, first Tormentor, scoreboard and, with a parsed replay, the lead and the lanes.
    The date opens the game like any match; one without a replay has a button there that requests it.
  </p>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th></th>
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
          {@const open = unfolded.includes(g.match_id)}
          <tr>
            <td>
              <button class="unfold" aria-expanded={open} aria-label="Details of the game on {date(g.start_time)}" onclick={() => unfold(g.match_id)}>
                {open ? '▾' : '▸'}
              </button>
            </td>
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
          {#if open}
            <tr class="more">
              <td colspan="10">
                {#if g.draft.length}
                  <h3>Draft</h3>
                  <ol class="order" aria-label="Picks and bans in draft order">
                    {#each g.draft as d, i}
                      {@const what = `${i + 1}. ${d.ours ? 'Their' : 'Enemy'} ${d.pick ? 'pick' : 'ban'}: ${heroName(d.hero_id)}`}
                      <li class:ours={d.ours} class:ban={!d.pick}>
                        <img src={heroIcon(d.hero_id)} alt={what} title={what} width="32" height="32" loading="lazy" />
                      </li>
                    {/each}
                  </ol>
                  <p class="muted">Their picks and bans sit high, the enemy's low; bans are greyed.</p>
                {/if}
                <p>
                  {#if g.tormentor}
                    First Tormentor at {clock(g.tormentor.time)}, taken by {g.tormentor.taken ? 'them' : 'the enemy'} with
                    {g.tormentor.enemies_dead} heroes of the other side dead and a net worth lead of {lead(g.tormentor.lead)}.
                  {:else if g.replay}
                    No Tormentor was taken.
                  {/if}
                  {#if g.first_blood !== null}They {g.first_blood ? 'drew' : 'gave up'} first blood.{/if}
                </p>
                <Match id={String(g.match_id)} brief />
              </td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
  </div>
  {:else}
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
            <WardHeat wards={p.wards} games={p.parsed} label="Heatmap of the wards {p.name ?? p.account_id} placed" byGame />
            <p class="muted">
              From the {p.replays} of their {p.games} tournament games whose replay is parsed, and {p.usual_replays} of
              their usual matches with a parsed replay.
            </p>
          {:else}
            <p class="muted">
              None of their games has a parsed replay yet, and wards are only in replays. Request the replays under
              "First moves" on the General tab, or with the button on a game's page.
            </p>
          {/if}
          {#if p.usual_waiting === null}
            <p class="muted">Refresh fetches the replays of their usual matches from the last 30 days, about ten a minute.</p>
          {:else if p.usual_waiting}
            <p class="muted">{p.usual_waiting} more of their usual matches from the last 30 days wait for their replay.</p>
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
  {/if}
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
  .tabs {
    margin: 4px 0 6px;
  }
  .player {
    margin-bottom: 6px;
  }
  .name {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .name img {
    object-fit: contain;
  }
  /* the two maps side by side, one under the other when there is no room */
  .pair {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 0 32px;
    align-items: start;
  }
  .lanes {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 12px;
  }
  .lane {
    padding: 14px;
  }
  .lane h3,
  .more h3 {
    margin: 0 0 10px;
    font-size: 15px;
  }
  .versus {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 10px;
    color: var(--text-2);
  }
  /* a rope pulled from the middle, as on a game's lanes */
  .tug {
    display: grid;
    grid-template-columns: 1fr 1fr;
    height: 8px;
    background: var(--raised);
    border-radius: 2px;
    overflow: hidden;
  }
  .tug span {
    display: flex;
  }
  .tug span:first-child {
    justify-content: flex-end;
    border-right: 1px solid var(--text-2);
  }
  .tug .won {
    background: var(--good);
  }
  .tug .lost {
    background: var(--critical);
  }
  .standing {
    margin: 10px 0 0;
  }
  .unfold {
    padding: 2px 6px;
    background: none;
    border: 0;
    color: var(--text-2);
    cursor: pointer;
  }
  .more > td {
    padding: 12px 12px 18px;
    background: var(--page);
  }
  /* draft order left to right; their turns sit high, the enemy's low */
  .order {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .order li {
    margin-top: 16px;
  }
  .order li.ours {
    margin: 0 0 16px;
  }
  .order li.ban img {
    filter: grayscale(1);
    opacity: 0.5;
  }
  /* the busier a role is for that pick, the deeper the cell: a pick that is always mid stands out */
  .draft td.num {
    background: color-mix(in srgb, var(--series-1) calc(var(--share) * 0.6), transparent);
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
