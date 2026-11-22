<script lang="ts">
  import { TEAMMATE_GAMES, TEAMMATE_MATCHES, clock, get, percent, post, type Account, type MatchRow, type WardSpot } from './lib/api'
  import { heroIcon, heroName, heroPortrait } from './lib/constants.svelte'
  import Heroes from './Heroes.svelte'
  import Matches from './Matches.svelte'
  import Teammates from './Teammates.svelte'
  import RoleWheel, { tally } from './lib/RoleWheel.svelte'
  import WardHeat from './lib/WardHeat.svelte'
  import WinRate from './lib/WinRate.svelte'
  import Count from './lib/Count.svelte'

  let {
    query,
    account,
    tab,
    ontracked,
  }: { query: string; account: Account | undefined; tab: string; ontracked: () => void } = $props()

  let tracking = $state(false)
  let tracked = $state('') // what the last "Add teammates" did
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
  const TABS = { overview: 'Overview', matches: 'Matches', heroes: 'Heroes', laning: 'Laning', warding: 'Warding', teammates: 'Teammates' }
  const shown = $derived<keyof typeof TABS>(tab in TABS ? (tab as keyof typeof TABS) : 'overview')
  // the server narrows to every filter, the role, the queue and the number of matches among them; newest first
  let recent = $state<MatchRow[]>([])
  let wards = $state.raw<WardSpot[]>([]) // of the same matches
  let error = $state('')

  $effect(() => {
    let current = true
    Promise.all([get<MatchRow[]>('matches', query), get<typeof wards>('wards', query)]).then(
      ([found, placed]) => current && ((recent = found), (wards = placed), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const TOP_HEROES = 10
  const LANES = 5 // matches in the best and in the worst lanes
  const EVEN = 500 // a lane within this much net worth at 10:00 counts as even
  const wins = $derived(recent.filter((r) => r.win).length)
  const share = (part: number) => `${percent(part, recent.length)}%`
  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString(undefined, { dateStyle: 'medium' })

  const heroes = $derived(tally(recent))
  const roles = $derived(recent.map((r) => ({ ...r, role: r.position })))

  const signed = (n: number) => `${n > 0 ? '+' : ''}${Math.round(n).toLocaleString()}`
  const note = (r: MatchRow) =>
    `${heroName(r.hero_id)}, ${date(r.start_time)}: ${r.win ? 'won' : 'lost'}` +
    (r.lane_nw_diff === null ? '' : `, lane ${signed(r.lane_nw_diff)} net worth at 10:00`)

  const parsed = $derived(recent.filter((r) => r.replay_state === 'parsed').length)
  /** The mean of a replay stat over the matches that have it, null with none */
  function mean(values: (number | null)[]) {
    const known = values.filter((v) => v !== null)
    return known.length ? known.reduce((a, b) => a + b, 0) / known.length : null
  }
  const wardAverages = $derived([
    ['Observers bought', mean(recent.map((r) => r.obs_bought)), 'per match'],
    ['Sentries bought', mean(recent.map((r) => r.sen_bought)), 'per match'],
    ['Enemy wards destroyed', mean(recent.map((r) => r.wards_destroyed)), 'per match'],
    ['Observer uptime', mean(recent.map((r) => r.obs_lifetime)), 'how long an observer stood'],
  ] as const)

  // ---- laning: averages of the first 10 minutes. 'signed' stats are differences to the enemy lane, 'tenths' are counts
  let laneHero = $state(0) // the hero picked above the laning numbers, 0 for every hero
  // a hero no longer among the matches shown (another role, fewer matches) falls back to every hero
  const onHero = $derived(heroes.some((h) => h.hero_id === laneHero))
  const laneGames = $derived(onHero ? recent.filter((r) => r.hero_id === laneHero) : recent)
  // ---- the strip: one column per match, oldest on the left, of the hero picked for laning
  const strip = $derived([...laneGames].reverse())
  const reach = $derived(Math.max(1000, ...laneGames.map((r) => Math.abs(r.lane_nw_diff ?? 0))))
  const at10 = (key: keyof MatchRow) => mean(laneGames.map((r) => r[key] as number | null))
  const laneMatches = $derived(laneGames.filter((r) => r.xp_at_10 !== null).length)
  // the leads compare the whole lane, or you with the enemy in the mirrored position (see Mirror in IMPLEMENTATION.md)
  let versus = $state<'lane' | 'mirror'>('lane')
  const VERSUS = { lane: 'Your lane vs theirs', mirror: 'You vs your mirror' }
  const lead = $derived(versus === 'lane'
    ? { nw: 'lane_nw_diff', cs: 'lane_cs_diff', unit: 'your lane minus the enemy lane at 10:00' } as const
    : { nw: 'mirror_nw_diff', cs: 'mirror_cs_diff', unit: 'you minus the enemy in your mirrored position at 10:00' } as const) // prettier-ignore
  const laning = $derived([
    ['General', [
      ['Net worth lead', at10(lead.nw), lead.unit, 'signed'],
      ['Last-hit lead', at10(lead.cs), lead.unit, 'signed'],
      ['Last hits', at10('last_hits_at_10'), 'creeps and neutrals at 10:00', ''],
      ['Denies', at10('denies_at_10'), 'at 10:00', ''],
      ['Net worth', at10('net_worth_at_10'), 'at 10:00', ''],
      ['Experience', at10('xp_at_10'), 'at 10:00', ''],
      ['Kills', at10('kills_by_10'), 'before 10:00', 'tenths'],
      ['Deaths', at10('deaths_by_10'), 'before 10:00', 'tenths'],
      ['Lotuses collected', at10('lotuses'), 'per match', 'tenths'],
      ['Camps pulled', at10('camps_pulled'), 'per match', 'tenths'],
      ['Twin gate trips', at10('twin_gates'), 'per match', 'tenths'],
    ]],
    ['Damage to heroes before 10:00', [
      ['You dealt', at10('damage_at_10'), 'to enemy heroes', ''],
      ['Your lane dealt', at10('lane_damage_at_10'), 'you and your lane partner together', ''],
      ['Enemy lane dealt', at10('enemy_lane_damage_at_10'), 'the heroes you laned against, to your lane', ''],
      ['You took', at10('damage_taken_at_10'), 'from all enemy heroes', ''],
    ]],
  ] as const) // prettier-ignore
  // the matches with the biggest and smallest net worth lead; with few matches each list takes its half, so none is in both
  const extremes = $derived.by(() => {
    const ranked = laneGames.filter((r) => r[lead.nw] !== null).sort((a, b) => b[lead.nw]! - a[lead.nw]!)
    const best = ranked.slice(0, Math.min(LANES, Math.ceil(ranked.length / 2)))
    return [['Best lanes', best], ['Worst lanes', ranked.slice(best.length).reverse().slice(0, LANES)]] as const
  })
  const shownStat = (value: number | null, kind: string) =>
    value === null ? '–' : kind === 'signed' ? signed(value) : kind === 'tenths' ? value.toFixed(1) : Math.round(value).toLocaleString()

  // ---- activity: games per day over the last 3 months, one column per week from Monday
  const dayOf = (d: Date) => d.toLocaleDateString('en-CA')
  const perDay = $derived(
    recent.reduce((m, r) => {
      const key = dayOf(new Date(r.start_time * 1000))
      const day = m.get(key) ?? { games: 0, wins: 0 }
      return m.set(key, { games: day.games + 1, wins: day.wins + r.win })
    }, new Map<string, { games: number; wins: number }>()),
  )
  const weeks = $derived.by(() => {
    const day = new Date()
    day.setHours(0, 0, 0, 0)
    day.setMonth(day.getMonth() - 3)
    day.setDate(day.getDate() - ((day.getDay() + 6) % 7)) // back to that week's Monday
    const found: { date: Date; games: number; wins: number }[][] = []
    for (const now = new Date(); day <= now; day.setDate(day.getDate() + 1)) {
      if (day.getDay() === 1) found.push([])
      found.at(-1)!.push({ date: new Date(day), games: 0, wins: 0, ...perDay.get(dayOf(day)) })
    }
    return found
  })
  const active = $derived(weeks.flat().filter((d) => d.games))
  const busiest = $derived(Math.max(1, ...active.map((d) => d.games)))
  // yellow at a 50 % win rate, redder down to full red at 25 %, greener up to full green at 75 %; the circle's area grows
  // with the games
  const tint = (d: { games: number; wins: number }) => {
    const lean = Math.min(1, Math.abs((4 * d.wins) / d.games - 2)) // 0 at 50 %, 1 at 25 % or 75 % and beyond
    return `color-mix(in oklab, var(${d.wins * 2 < d.games ? '--dire' : '--radiant'}) ${100 * lean}%, var(--series-4))`
  }
  const dot = (games: number) => `${Math.max(5, 18 * Math.sqrt(games / busiest))}px`
  const dayNote = (d: { date: Date; games: number; wins: number }) =>
    `${d.date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}: ${d.games || 'no'} ${d.games === 1 ? 'game' : 'games'}` +
    (d.games ? `, ${d.wins} won (${percent(d.wins, d.games)}%)` : '')

  const laned = $derived(recent.filter((r) => r.lane_nw_diff !== null))
  const lanes = $derived({
    won: laned.filter((r) => r.lane_nw_diff! > EVEN).length,
    even: laned.filter((r) => Math.abs(r.lane_nw_diff!) <= EVEN).length,
    lost: laned.filter((r) => r.lane_nw_diff! < -EVEN).length,
  })
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if recent.length === 0}
  <p class="muted">No matches for these filters.</p>
{:else}
  <header class="title">
    <h2>
      {#if account?.avatar}<img class="avatar" src={account.avatar} alt="" width="40" height="40" />{/if}
      {account?.label ?? account?.account_id}
    </h2>
    <p class="muted">{recent.length} matches for these filters</p>
    <p class="track">
      <span class="muted" role="status">{tracked}</span>
      <button
        class="action"
        onclick={addTeammates}
        disabled={tracking}
        title="Adds every player with {TEAMMATE_GAMES} or more games on their team in their last {TEAMMATE_MATCHES} matches"
      >
        {tracking ? 'Adding…' : 'Add frequent teammates'}
      </button>
    </p>
  </header>

  <div class="tabs" role="tablist" aria-label="Profile">
    {#each Object.entries(TABS) as [id, title]}
      <button role="tab" aria-selected={shown === id} onclick={() => (location.hash = id === 'overview' ? 'profile' : `profile/${id}`)}>{title}</button>
    {/each}
  </div>

  {#if shown === 'matches'}
    <Matches {query} />
  {:else if shown === 'heroes'}
    <Heroes {query} matches={recent} />
  {:else if shown === 'teammates'}
    <Teammates {query} />
  {:else if shown === 'overview'}
  <dl class="card numbers">
    <div>
      <dt>Win rate</dt>
      <dd>{share(wins)}</dd>
      <dd class="muted">{wins} won, {recent.length - wins} lost</dd>
    </div>
    <div>
      <dt>Lanes won, even, lost</dt>
      <dd><span class="good">{lanes.won}</span> – {lanes.even} – <span class="bad">{lanes.lost}</span></dd>
      <dd class="muted">even is within {EVEN} net worth at 10:00</dd>
    </div>
    <div>
      <dt>Ranked</dt>
      <dd>{share(recent.filter((r) => r.lobby_type === 7).length)}</dd>
      <dd class="muted">of these matches</dd>
    </div>
    <div>
      <dt>With tracked players</dt>
      <dd>{share(recent.filter((r) => r.with_tracked).length)}</dd>
      <dd class="muted">another tracked account on the team</dd>
    </div>
  </dl>
  <div class="overview">
    <section class="card roles">
      <RoleWheel games={roles} none="No replay" />
    </section>

    <section class="card">
      <table>
        <thead>
          <tr><th>Hero</th><th>Matches</th><th>Win rate</th><th class="num">K / D / A</th></tr>
        </thead>
        <tbody>
          {#each heroes.slice(0, TOP_HEROES) as h (h.hero_id)}
            <tr>
              <td><img class="icon" src={heroPortrait(h.hero_id)} alt={heroName(h.hero_id)} title={heroName(h.hero_id)} width="44" height="25" loading="lazy" /></td>
              <td><Count games={h.games} max={heroes[0].games} /></td>
              <td><WinRate wins={h.wins} games={h.games} /></td>
              <td class="num">{(h.kills / h.games).toFixed(1)} / {(h.deaths / h.games).toFixed(1)} / {(h.assists / h.games).toFixed(1)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if heroes.length > TOP_HEROES}
        <p class="muted more">The {TOP_HEROES} most played of {heroes.length} heroes. The Heroes tab has them all.</p>
      {/if}
    </section>
  </div>

  <section class="card activity">
    <div class="calendar" role="img" aria-label="Games and win rate per day over the last 3 months: {active.length} days played">
      <div class="week">
        <span class="month"></span>
        {#each weeks[0] as d}<span class="weekday">{d.date.toLocaleDateString(undefined, { weekday: 'short' })}</span>{/each}
      </div>
      {#each weeks as week}
        {@const first = week.find((d) => d.date.getDate() === 1)}
        <div class="week">
          <span class="month">{first ? first.date.toLocaleDateString(undefined, { month: 'short' }) : ''}</span>
          {#each week as d}
            <i title={dayNote(d)}>{#if d.games}<b style:background={tint(d)} style:width={dot(d.games)} style:height={dot(d.games)}></b>{/if}</i>
          {/each}
        </div>
      {/each}
    </div>
    <div class="muted">
      <h3>Activity</h3>
      <p>
        {active.reduce((n, d) => n + d.games, 0)} games on {active.length} days in the last 3 months, at most {busiest}
        in one day. One square per day, a column per week from Monday. The bigger the circle, the more games that day; its
        colour is the day's win rate: yellow at half, the redder the more were lost, full red at 25 % or less, the greener the
        more were won, full green at 75 % or more.
      </p>
    </div>
  </section>

  {:else if shown === 'laning'}
  <label class="pick">
    Hero
    <select value={onHero ? laneHero : 0} onchange={(e) => (laneHero = +e.currentTarget.value)}>
      <option value={0}>All heroes ({recent.length})</option>
      {#each heroes as h (h.hero_id)}<option value={h.hero_id}>{heroName(h.hero_id)} ({h.games})</option>{/each}
    </select>
  </label>
  <div class="choice" role="group" aria-label="Whom the leads compare you with">
    {#each Object.entries(VERSUS) as [id, title]}
      <button aria-pressed={versus === id} onclick={() => (versus = id as typeof versus)}>{title}</button>
    {/each}
  </div>
  {#each laning as [title, stats]}
    <h3 class="group">{title}</h3>
    <dl class="card numbers">
      {#each stats as [label, value, unit, kind]}
        <div>
          <dt>{label}</dt>
          <dd class:good={kind === 'signed' && value !== null && value > 0} class:bad={kind === 'signed' && value !== null && value < 0}>
            {shownStat(value, kind)}
          </dd>
          <dd class="muted">{unit}</dd>
        </div>
      {/each}
    </dl>
  {/each}
  <section class="card form">
    <div class="strip" class:dense={laneGames.length > 25} class:packed={laneGames.length > 100}>
      {#each strip as r (r.match_id)}
        {@const nw = r.lane_nw_diff}
        <a href="#match/{r.match_id}" title={note(r)} aria-label={note(r)}>
          <img src={heroIcon(r.hero_id)} alt="" width="22" height="22" loading="lazy" />
          <span class="lane">
            {#if nw !== null}
              <i class={nw < 0 ? 'behind' : 'ahead'} style:height="{Math.max(2, (50 * Math.abs(nw)) / reach)}%"></i>
            {/if}
          </span>
          <i class="dot {r.win ? 'won' : 'lost'}"></i>
        </a>
      {/each}
    </div>
    <p class="muted">
      One column per match, the oldest on the left. The bar is the net worth lead of the player's lane at 10:00: up when
      ahead, down when behind. A match without a parsed replay has no bar. The dot is the result.
    </p>
  </section>

  {#each extremes as [title, games]}
    <h3 class="group">{title}</h3>
    {#if games.length}
      <section class="card">
        <table>
          <thead>
            <tr><th>Match</th><th>Your heroes</th><th>Enemy heroes</th><th>Result</th><th class="num">Net worth lead</th><th class="num">Last-hit lead</th><th class="num">Deaths</th></tr>
          </thead>
          <tbody>
            {#each games as r (r.match_id)}
              {@const nw = r[lead.nw]}
              {@const cs = r[lead.cs]}
              <tr>
                <td><a href="#match/{r.match_id}">{date(r.start_time)}</a></td>
                <!-- the whole lane on both sides, whichever lead is picked: you first, then your lane partners -->
                {#each [[r.hero_id, ...r.lane_allies], r.lane_enemies] as side}
                  <td class="laners">
                    {#each side as hero}<img src={heroPortrait(hero)} alt={heroName(hero)} title={heroName(hero)} width="64" height="36" loading="lazy" />{/each}
                  </td>
                {/each}
                <td><span class="dot {r.win ? 'won' : 'lost'}"></span>{r.win ? 'Won' : 'Lost'}</td>
                <td class="num" class:good={nw !== null && nw > 0} class:bad={nw !== null && nw < 0}>{shownStat(nw, 'signed')}</td>
                <td class="num" class:good={cs !== null && cs > 0} class:bad={cs !== null && cs < 0}>{shownStat(cs, 'signed')}</td>
                <td class="num">{shownStat(r.deaths_by_10, 'tenths')}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {:else}
      <p class="muted">No match with a parsed replay here.</p>
    {/if}
  {/each}
  <p class="muted laning">
    Averages over the {laneMatches} of these {laneGames.length} matches{onHero ? ` on ${heroName(laneHero)}` : ''} that have a parsed replay and lasted 10 minutes. Your
    lane is you and the allies who laned with you, the enemy lane the heroes you laned against; in the mid lane that is
    usually one hero each. Damage counts only hits on heroes, after armour and resistances, as the replay's combat log
    records it. Lotuses, pulls and twin gate trips count the whole match. With "You vs your mirror" the leads compare
    you alone with the enemy whose position mirrors yours: 1 with 3, 2 with 2, 4 with 5. The best and worst lanes
    are the {LANES} of these matches with the biggest and the smallest net worth lead at 10:00, each with every hero of
    both lanes, yours first; click a date to open the match.
  </p>
  {:else}
  <section class="card vision">
    <div>
      <WardHeat {wards}games={recent.filter((r) => r.replay_state === 'parsed')} label="Heatmap of the wards {account?.label ?? 'the player'} placed in these matches" />
    </div>
    <div class="muted">
      <dl class="wardstats">
        {#each wardAverages as [label, value, unit]}
          <div>
            <dt>{label}</dt>
            <dd>{value === null ? '–' : label === 'Observer uptime' ? clock(Math.round(value)) : value.toFixed(1)}</dd>
            <dd>{unit}</dd>
          </div>
        {/each}
      </dl>
      <h3>Wards placed</h3>
      <p>
        Where the wards went in the {parsed} of these {recent.length} matches that have a parsed replay. Every ward
        warms the map around its spot; red is a spot warded now and then, yellow to white the spots warded most.
      </p>
      <p>
        Radiant and Dire ward different places, so the map shows one side's games and one kind of ward at a time: the
        buttons above it switch between them. Scroll over the map to zoom (scrolling all the way out shows the whole map again), drag to move it, hover a spot for
        its count.
      </p>
      <p>
        The numbers above are averages over the same matches. Uptime is the mean time from placing an observer to its
        expiry or its destruction; one still standing when the game ended is left out.
      </p>
    </div>
  </section>
  {/if}
{/if}

<style>
  .title {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 4px 16px;
    margin: 8px 0 14px;
  }
  .title h2 {
    margin: 0;
    font-size: 28px;
    font-weight: 800;
    font-stretch: 125%;
  }
  .avatar {
    margin-right: 10px;
    border-radius: 4px;
    vertical-align: -6px;
  }
  .title p {
    margin: 0;
  }
  .track {
    margin-left: auto;
  }

  .overview {
    display: grid;
    grid-template-columns: minmax(300px, 5fr) 7fr;
    gap: 12px;
    margin-bottom: 12px;
  }
  @media (max-width: 900px) {
    .overview {
      grid-template-columns: 1fr;
    }
  }
  .roles {
    display: grid;
    align-content: center;
    padding: 18px;
  }
  .icon {
    display: block;
    object-fit: cover;
    border-radius: 3px;
  }
  .more {
    margin: 0;
    padding: 8px 12px;
    font-size: 13px;
  }

  .form {
    padding: 16px 18px 6px;
    margin-bottom: 12px;
  }
  .strip {
    display: flex;
    gap: 4px;
  }
  .strip a {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 4px 0;
    border-radius: 3px;
    text-decoration: none;
  }
  .strip a:hover {
    background: var(--raised);
  }
  .strip.dense {
    gap: 1px;
  }
  .strip.packed {
    gap: 0;
  }
  .strip.dense img {
    display: none;
  }
  /* the bar grows from a middle line: up when the lane was ahead, down when behind */
  .lane {
    position: relative;
    width: 100%;
    height: 84px;
    background: linear-gradient(var(--axis), var(--axis)) center / 100% 1px no-repeat;
  }
  .lane i {
    position: absolute;
    left: 22%;
    right: 22%;
    border-radius: 2px;
  }
  .lane .ahead {
    bottom: 50%;
    background: var(--text-2);
  }
  .lane .behind {
    top: 50%;
    background: var(--muted);
    opacity: 0.55;
  }
  .strip .dot {
    margin: 0;
  }
  .strip.dense .dot {
    width: 5px;
    height: 5px;
  }

  .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0 22px;
    margin-bottom: 18px;
    border-bottom: 1px solid var(--border);
  }
  .tabs button {
    padding: 10px 0 9px;
    font: inherit;
    font-weight: 500;
    color: var(--muted);
    background: none;
    border: 0;
    border-bottom: 2px solid transparent;
    cursor: pointer;
  }
  .tabs button:hover,
  .tabs button[aria-selected='true'] {
    color: var(--text);
  }
  .tabs button[aria-selected='true'] {
    border-bottom-color: var(--text);
  }

  .activity {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 32px;
    padding: 16px 18px;
    margin-bottom: 12px;
  }
  .activity h3 {
    margin: 0 0 8px;
    color: var(--text);
  }
  .activity p {
    max-width: 52ch;
    margin: 0;
  }
  .calendar {
    display: flex;
    gap: 3px;
  }
  .week {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .month {
    width: 22px; /* the name runs over into the next weeks */
    height: 18px;
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }
  .weekday {
    height: 22px;
    padding-right: 6px;
    font-size: 12px;
    line-height: 22px;
    color: var(--muted);
  }
  .week i {
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    background: var(--raised);
    border-radius: 3px;
  }
  .week b {
    border-radius: 50%;
  }

  .vision {
    display: grid;
    grid-template-columns: minmax(280px, 520px) minmax(200px, 1fr);
    gap: 8px 24px;
    padding: 16px 18px;
    margin-bottom: 12px;
  }
  @media (max-width: 900px) {
    .vision {
      grid-template-columns: 1fr;
    }
  }
  .vision h3 {
    margin: 0 0 8px;
    color: var(--text);
  }
  .vision p {
    max-width: 52ch;
  }
  .wardstats {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px 24px;
    max-width: 52ch;
    margin: 0 0 20px;
  }
  .wardstats dt + dd {
    color: var(--text);
  }

  .group {
    margin: 20px 0 8px;
  }
  .laners {
    white-space: nowrap;
  }
  .laners img {
    margin-right: 4px;
    object-fit: cover;
    border-radius: 3px;
    vertical-align: middle;
  }
  .pick select {
    margin-left: 6px;
  }
  .laning {
    max-width: 72ch;
  }
  .numbers {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    margin: 0 0 12px;
  }
  .numbers div {
    padding: 16px 18px;
    border-right: 1px solid var(--grid);
  }
  .numbers div:last-child {
    border: 0;
  }
  dt {
    color: var(--text-2);
  }
  dd {
    margin: 0;
    font-size: 13px;
  }
  dt + dd {
    font-size: 28px;
    font-weight: 800;
    font-stretch: var(--wide);
    font-variant-numeric: tabular-nums;
    line-height: 1.3;
  }
  .good {
    color: var(--good);
  }
  .bad {
    color: var(--critical);
  }
</style>
