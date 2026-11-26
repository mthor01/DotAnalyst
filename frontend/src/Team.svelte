<script lang="ts">
  import About from './lib/About.svelte'
  import { RECENT_GAMES, clock, get, percent, sortedBy, type TeamDetail, type TeamHero } from './lib/api'
  import { heroIcon, heroName } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'
  import Openings from './lib/Openings.svelte'
  import ReplaySign from './lib/ReplaySign.svelte'
  import RoleWheel from './lib/RoleWheel.svelte'
  import WardHeat from './lib/WardHeat.svelte'
  import Match from './Match.svelte'
  import { shownTab } from './lib/settings.svelte'

  let { id, query, onshown }: { id: string; query: string; onshown: (shown: { games: number; parsed: number } | null) => void } = $props()
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

  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString('en-GB', { dateStyle: 'medium' })
  const games = $derived(team?.games.length ?? 0)
  /** A count with its share of the team's games: 5 (17%) */
  const ofGames = (n: number) => (n ? `${n} (${percent(n, games)}%)` : '–')
  const rate = (part: number, whole: number) => (whole ? `${percent(part, whole)}%` : '–')
  // title, the number the column sorts by, and what the cell says. A rate of nothing sorts below every rate
  const COLUMNS: [string, (h: TeamHero) => number, (h: TeamHero) => string][] = [
    ['Games played', (h) => h.picked, (h) => (h.picked ? String(h.picked) : '–')],
    ['Win rate', (h) => (h.picked ? h.wins / h.picked : -1), (h) => rate(h.wins, h.picked)],
    ['Banned against them', (h) => h.banned_against, (h) => ofGames(h.banned_against)],
    ['Banned by them', (h) => h.banned, (h) => ofGames(h.banned)],
    ['Picked by enemy team', (h) => h.picked_against, (h) => ofGames(h.picked_against)],
    ['Open', (h) => h.open, (h) => ofGames(h.open)],
    ['Picked when open', (h) => (h.open ? h.picked / h.open : -1), (h) => rate(h.picked, h.open)],
  ]
  let sort = $state({ column: 0, descending: true }) // games played
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
  const TABS = ['Overview', 'Games', 'Players', 'Draft', 'General'] as const
  let picked = $state<(typeof TABS)[number]>('Overview')
  // a tab hidden on the Design page gives way to the first one shown
  const tab = $derived(shownTab('team', TABS.map((t) => t.toLowerCase()), picked.toLowerCase()))
  const stack = $derived(team?.players.filter((p) => p.main) ?? [])
  const others = $derived(team?.players.filter((p) => !p.main).sort((a, b) => b.last_played - a.last_played) ?? [])
  const STAND_IN_MONTHS = 3 // a player who stood in longer ago than this is a historical player
  const standInSince = (() => {
    const day = new Date()
    day.setMonth(day.getMonth() - STAND_IN_MONTHS)
    return day.getTime() / 1000
  })()
  const standIns = $derived(others.filter((p) => p.last_played >= standInSince))
  const historical = $derived(others.filter((p) => p.last_played < standInSince))
  /** The site's own profile for a tracked player, else OpenDota's */
  const profile = (account_id: number, tracked: boolean) =>
    tracked ? `#account/${account_id}` : `https://www.opendota.com/players/${account_id}`
  const sides = $derived(
    [true, false].map((radiant) => {
      const on = team?.games.filter((g) => g.radiant === radiant) ?? []
      return { title: radiant ? 'As Radiant' : 'As Dire', games: on.length, wins: on.filter((g) => g.win).length }
    }),
  )
  let unfolded = $state<number[]>([]) // the games whose row is open
  const unfold = (id: number) => (unfolded = unfolded.includes(id) ? unfolded.filter((o) => o !== id) : [...unfolded, id])
  // a click anywhere on the row unfolds it, except on its links and buttons, which do their own thing
  const unfoldRow = (e: MouseEvent, id: number) => !(e.target as Element).closest('a, button') && unfold(id)
  /** The parsed games where first blood is known */
  const bloods = $derived(team?.games.filter((g) => g.first_blood !== null) ?? [])
  const drew = $derived(bloods.filter((g) => g.first_blood).length)
  const LANE_NAMES = { safe: 'Safe lane', mid: 'Mid', off: 'Off lane' } as const
  /** One scale for the three lane bars: the largest mean net worth lead, at least 1000 */
  const laneBound = $derived(Math.max(1000, ...Object.values(team?.lanes ?? {}).map((l) => Math.abs(l.net_worth ?? 0))))
  /** The wards of all their players in the team's own games, for the General tab's map */
  const teamWards = $derived(team?.players.flatMap((p) => p.wards.filter((w) => w.league)) ?? [])
  const parsed = $derived(team?.games.filter((g) => g.replay).map((g) => ({ radiant: g.radiant, win: g.win })) ?? [])
  $effect(() => {
    onshown(team ? { games, parsed: parsed.length } : null)
    return () => onshown(null) // gone with the page, so another page's panel shows no stale count
  })
  const PICKS = ['1st pick (first phase)', '2nd pick (second phase)', '3rd pick (second phase)', '4th pick (second phase)', '5th pick (last phase)']
</script>

{#snippet face(p: TeamDetail['players'][number], size: number)}
  {#if p.avatar}
    <img class="face" src={p.avatar} alt="" width={size} height={size} loading="lazy" />
  {:else}
    <span class="face blank" style:width="{size}px" style:height="{size}px" aria-hidden="true">{(p.name ?? '?').slice(0, 1).toUpperCase()}</span>
  {/if}
{/snippet}

{#snippet bench(list: TeamDetail['players'])}
  <ul class="bench">
    {#each list as p (p.account_id)}
      <li>
        <a href={profile(p.account_id, p.tracked)} target={p.tracked ? undefined : '_blank'} rel="noopener">
          {@render face(p, 36)}
          <span><b>{p.name ?? `Player ${p.account_id}`}</b><br /><span class="muted">{p.position ? `Pos ${p.position}, ` : ''}{p.games} {p.games === 1 ? 'game' : 'games'}, last {date(p.last_played)}</span></span>
        </a>
      </li>
    {/each}
  </ul>
{/snippet}

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
    <p class="muted">No league games of theirs in this season and time frame. <a href="#tournaments/teams">All teams</a></p>
  {:else}
  <p class="muted">{games} league games, {wins} won ({percent(wins, games)}%). {seasons}. <a href="#tournaments/teams">All teams</a></p>

  <div class="choice tabs" role="group" aria-label="Part of the team page">
    {#each TABS as name}
      <button data-block="team.{name.toLowerCase()}" aria-pressed={tab === name.toLowerCase()} onclick={() => (picked = name)}>{name}</button>
    {/each}
  </div>

  {#if tab === 'overview'}
  <dl class="facts">
    <div><dt>Record</dt><dd>{wins}–{games - wins}</dd><dd class="muted">{percent(wins, games)}% won</dd></div>
    {#each sides as s}
      <div><dt>{s.title}</dt><dd>{s.wins}–{s.games - s.wins}</dd><dd class="muted">{s.games ? `${percent(s.wins, s.games)}% won` : 'no games'}</dd></div>
    {/each}
    <div>
      <dt>First blood</dt>
      <dd>{bloods.length ? `${percent(drew, bloods.length)}%` : '–'}</dd>
      <dd class="muted">{bloods.length ? `of ${bloods.length} parsed games` : 'no parsed game'}</dd>
    </div>
    <div>
      <dt>Last {Math.min(RECENT_GAMES, games)} games</dt>
      <dd class="form">
        {#each team.games.slice(0, RECENT_GAMES).reverse() as g (g.match_id)}
          <a href="#match/{g.match_id}" class="dot {g.win ? 'won' : 'lost'}" title="{date(g.start_time)}: {g.win ? 'won' : 'lost'} against {g.opponent || 'no team'}" aria-label="{date(g.start_time)}, {g.win ? 'won' : 'lost'}"></a>
        {/each}
      </dd>
      <dd class="muted">oldest to newest</dd>
    </div>
  </dl>

  <div class="contents" data-block="team.overview.stack">
  <h2>Main stack</h2>
  <p class="muted">The five players seen most in their last {RECENT_GAMES} games.<About>The five players seen most in their last {RECENT_GAMES} games; a tie goes to whoever played more lately. The bar under a player fills one step per game of those. A name opens the player's profile here when the site tracks them, else on OpenDota.</About></p>
  <ol class="lineup">
    {#each stack as p (p.account_id)}
      <li>
        <a class="member" href={profile(p.account_id, p.tracked)} target={p.tracked ? undefined : '_blank'} rel="noopener">
          {@render face(p, 112)}
          <b>{p.name ?? `Player ${p.account_id}`}</b>
        </a>
        <span class="presence" role="img" aria-label="In {p.recent} of the last {RECENT_GAMES} games">
          {#each { length: RECENT_GAMES } as _, i}<i class:on={i < p.recent}></i>{/each}
        </span>
        <span class="muted">{p.position ? `Pos ${p.position}, ` : ''}{p.games} games{p.tracked ? ', tracked' : ''}</span>
        {@render icons(p.heroes.slice(0, 3).map((h) => h.hero_id))}
      </li>
    {/each}
  </ol>

  </div>

  <div class="contents" data-block="team.overview.standins">
  <h2>Stand-ins</h2>
  {#if standIns.length}
    {@render bench(standIns)}
  {:else}
    <p class="muted">Nobody else played for them in the last {STAND_IN_MONTHS} months of these games.</p>
  {/if}
  </div>

  <div class="contents" data-block="team.overview.history">
  {#if historical.length}
    <h2>Historical players</h2>
    <p class="muted">Played for them, but not in the last {STAND_IN_MONTHS} months.</p>
    {@render bench(historical)}
  {/if}

  </div>

  {:else if tab === 'general'}
  <div class="pair">
    <section data-block="team.general.wards">
      <h2>Wards placed</h2>
      {#if parsed.length}
        <p class="muted">Every ward of their {parsed.length} parsed games.<About>Every ward their players placed in the {parsed.length} of their {games} games whose replay is parsed; their usual matches are on each player's own map under Players.</About></p>
        <WardHeat wards={teamWards} games={parsed} label="Heatmap of the wards the team placed in its tournament games" />
      {:else}
        <p class="muted">None of their games has a parsed replay yet, and wards are only in replays. Request the replays under "First moves".</p>
      {/if}
    </section>
    <section data-block="team.general.moves">
      <h2>First moves</h2>
      <p class="muted">Their paths up to 0:30, last six games on one side.<About>Where their five heroes walked from the start of the pre-game to 0:30, in their last six games on one side. One colour per game; the button above the map switches between Radiant and Dire, the buttons beside it switch games on and off, the slider moves the clock.</About></p>
      <Openings games={team.games} onfetched={() => (fetched += 1)} />
    </section>
  </div>

  <div class="contents" data-block="team.general.blood">
  <h2>First blood</h2>
  {#if bloods.length}
    <p>They drew first blood in {drew} of the {bloods.length} games whose replay is parsed ({percent(drew, bloods.length)}%).</p>
  {:else}
    <p class="muted">Not known: none of their games has a parsed replay.</p>
  {/if}

  </div>

  <div class="contents" data-block="team.general.lanes">
  <h2>Lanes at 10:00</h2>
  <p class="muted">Each lane at 10:00, their heroes against the enemy.<About>Their heroes in each lane against the enemy's there, at 10:00 of the parsed games where both sides had a hero in it. The lead is theirs minus the enemy's, averaged over those games; the bar grows to the side ahead in net worth.</About></p>
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

  </div>

  <div class="contents" data-block="team.general.tormentor">
  <h2>First Tormentor</h2>
  <p class="muted">First Tormentor of {team.tormentors.games} parsed games.<About>The first Tormentor of each of the {team.tormentors.games} games whose replay is parsed, by who took it. Time, heroes dead and lead are averages over those games: the dead are the other side's, the lead is the taker's net worth minus the other side's.</About></p>
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

  </div>

  <div class="contents" data-block="team.general.runes">
  <h2>Wisdom runes</h2>
  <p class="muted">Wisdom runes from 7:00 on.<About>Every wisdom rune of their parsed games, from 7:00 on. They contested one when at least one of their heroes came within ten cells of it between 20 seconds before it appeared and its pickup; heroes and the net worth lead are averages over the ones they contested. Kills and deaths per game count the heroes that died within those ten cells from then until 15 seconds after the pickup.</About></p>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th></th><th class="num">Runes</th><th class="num">Contested</th><th class="num">Heroes they brought</th>
          <th class="num">Taken by them</th><th class="num">Net worth lead when contested</th>
          <th class="num">Kills per game</th><th class="num">Deaths per game</th>
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
            <td class="num">{w.kills === null ? '–' : one(w.kills)}</td>
            <td class="num">{w.deaths === null ? '–' : one(w.deaths)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  </div>

  {:else if tab === 'draft'}
  <div class="contents" data-block="team.draft.heroes">
  <h2>Heroes in their drafts</h2>
  <p class="muted">Open: not banned, not picked by the enemy.<About>A hero is open in a game when neither side banned it and the enemy team did not pick it. The percentages beside a count are of their {games} games; the win rate is of the games they played the hero, and picked when open of the games it was open. A hero banned against them often and picked nearly every time it is open is worth a ban.</About></p>
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

  </div>

  <div class="contents" data-block="team.draft.roles">
  <h2>Roles in their draft</h2>
  <p class="muted">The position each pick went on to play.<About>Which position the hero of each of their picks went on to play, in the {team.draft[0].reduce((a, b) => a + b, 0)} of their games whose replay is parsed. In Captains Mode a team picks once in the first phase, three times in the second and once in the last. The percentages are of the row.</About></p>
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
  </div>

  {:else if tab === 'games'}
  <h2>Games</h2>
  <p class="muted">Click a game to unfold it, ↗ opens it.<About>Unfolded: its draft, first Tormentor, scoreboard and, with a parsed replay, the lead and the lanes. One without a replay has a button under Replay that requests it.</About></p>
  <div class="card tall">
    <table>
      <thead>
        <tr>
          <th></th>
          <th>Date</th>
          <th>Against</th>
          <th>Result</th>
          <th>Picks <small class="muted">them / enemy</small></th>
          <th>Bans <small class="muted">by them / by the enemy</small></th>
          <th>Replay</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each team.games as g (g.match_id)}
          {@const open = unfolded.includes(g.match_id)}
          <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions (the arrow button is the keyboard way) -->
          <tr class="folds" onclick={(e) => unfoldRow(e, g.match_id)}>
            <td>
              <button class="unfold" aria-expanded={open} aria-label="Details of the game on {date(g.start_time)}" onclick={() => unfold(g.match_id)}>
                {open ? '▾' : '▸'}
              </button>
            </td>
            <td class="when">{date(g.start_time)}<small class="muted">{g.league}</small></td>
            <td>
              {#if g.opponent_id}
                <a href="#team/{g.opponent_id}">{g.opponent || `Team ${g.opponent_id}`}</a>
              {:else}
                <span class="muted">No team</span>
              {/if}
            </td>
            <td><span class="dot {g.win ? 'won' : 'lost'}"></span>{g.win ? 'Won' : 'Lost'}</td>
            <td class="sides">{@render icons(g.picks)}{@render icons(g.picks_against)}</td>
            <td class="sides">{@render icons(g.bans)}{@render icons(g.bans_against)}</td>
            <td class="muted"><ReplaySign match_id={g.match_id} state={g.replay_state} start_time={g.start_time} /></td>
            <td><a class="open" href="#match/{g.match_id}" title="Open the game" aria-label="Open the game on {date(g.start_time)}">↗</a></td>
          </tr>
          {#if open}
            <tr class="more">
              <td colspan="8">
                <Match id={String(g.match_id)} brief notes={g.radiant ? ['Them', 'Enemy'] : ['Enemy', 'Them']} />
                <p>
                  {#if g.tormentor}
                    First Tormentor at {clock(g.tormentor.time)}, taken by {g.tormentor.taken ? 'them' : 'the enemy'} with
                    {g.tormentor.enemies_dead} heroes of the other side dead and a net worth lead of {lead(g.tormentor.lead)}.
                  {:else if g.replay}
                    No Tormentor was taken.
                  {/if}
                  {#if g.first_blood !== null}They {g.first_blood ? 'drew' : 'gave up'} first blood.{/if}
                </p>
              </td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
  </div>
  {:else}
  <h2>Players</h2>
  <p class="muted">Click a player for their heroes and wards.<About>Everyone who played a league game for them. Click a player for their heroes, with the averages of a game on each, and for where they place their wards.</About></p>
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
            <p class="muted">{p.replays} tournament and {p.usual_replays} usual replays.<About>From the {p.replays} of their {p.games} tournament games whose replay is parsed, and {p.usual_replays} of their usual matches with a parsed replay.</About></p>
          {:else}
            <p class="muted">
              None of their games has a parsed replay yet, and wards are only in replays. Request the replays under
              "First moves" on the General tab, or with the button on a game's page.
            </p>
          {/if}
          {#if p.usual_waiting === null}
            <p class="muted">Refresh fetches the replays of their usual matches from the last 90 days, about ten a minute.</p>
          {:else if p.usual_waiting}
            <p class="muted">{p.usual_waiting} more of their usual matches from the last 90 days wait for their replay.</p>
          {/if}
        </section>
        <section class="outside">
          <h3>Their last {p.outside.length || ''} games outside the league</h3>
          {#if p.outside.length}
            <RoleWheel games={p.outside} none="Lane unknown" />
            <p class="muted">From OpenDota's list of their games.<About>From OpenDota's list of their games, without league and lobby games, whatever the filters above. The lane is OpenDota's, known only for the games it parsed.</About></p>
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
  /* their side on top, the enemy's below */
  .sides .icons + .icons {
    margin-top: 3px;
    padding-top: 3px;
    border-top: 1px solid var(--grid);
  }
  .when small {
    display: block;
    font-size: 11px;
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
  .facts {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 40px;
    margin: 14px 0 8px;
  }
  .facts dt {
    color: var(--text-2);
    font-size: 13px;
  }
  .facts dd {
    margin: 2px 0 0;
    font-size: 22px;
    font-variant-numeric: tabular-nums;
  }
  .facts dd.muted {
    font-size: 13px;
  }
  .form {
    display: flex;
    gap: 2px;
    padding-top: 8px;
  }
  /* the lineup: five tall portraits on one floor, a team photo more than a table */
  .lineup {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 14px;
    margin: 0;
    padding: 18px;
    list-style: none;
    background: linear-gradient(to top, var(--raised), var(--surface) 70%);
    border-radius: 6px;
  }
  .lineup li {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    text-align: center;
  }
  .member {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    color: var(--text);
    text-decoration: none;
  }
  .member .face {
    border-radius: 8px;
    box-shadow: 0 0 0 2px var(--page), 0 0 0 4px var(--axis);
  }
  .member:hover .face,
  .member:focus-visible .face {
    box-shadow: 0 0 0 2px var(--page), 0 0 0 4px var(--series-1);
  }
  .member:hover b {
    text-decoration: underline;
  }
  .face {
    display: block;
    flex: none;
    object-fit: cover;
    border-radius: 50%;
  }
  .face.blank {
    display: grid;
    place-items: center;
    background: var(--axis);
    color: var(--text-2);
    font-weight: 600;
  }
  .member .blank {
    font-size: 44px;
  }
  .bench .blank {
    font-size: 16px;
  }
  .presence {
    display: flex;
    gap: 2px;
  }
  .presence i {
    width: 9px;
    height: 5px;
    border-radius: 1px;
    background: var(--axis);
  }
  .presence i.on {
    background: var(--series-1);
  }
  .bench {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 28px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .bench a {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--text);
    text-decoration: none;
  }
  .bench a:hover b {
    text-decoration: underline;
  }
</style>
