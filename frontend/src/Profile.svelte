<script lang="ts">
  import About from './lib/About.svelte'
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
    positions,
    onpositions,
  }: {
    query: string
    account: Account | undefined
    tab: string
    ontracked: () => void
    positions: (1 | 2 | 3 | 4 | 5)[] // the Role filter's
    onpositions: (positions: (1 | 2 | 3 | 4 | 5)[]) => void
  } = $props()

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
  const TABS = { overview: 'Overview', general: 'General', matches: 'Matches', heroes: 'Heroes', laning: 'Laning', warding: 'Warding', teammates: 'Teammates' }
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
  // the General tab's trend: as many matches as shown, under the same filters, from before the oldest one shown
  let before = $state.raw<MatchRow[]>([])
  $effect(() => {
    const oldest = recent.at(-1)
    before = []
    if (shown !== 'general' || !oldest) return
    let current = true
    const params = new URLSearchParams(query)
    const day = new Date(oldest.start_time * 1000)
    day.setDate(day.getDate() - 1)
    // shortcut: the API filters by whole days, so earlier matches on the oldest one's day are left out of both sets; a start_time bound if that matters
    params.delete('date_from')
    params.set('date_to', day.toLocaleDateString('en-CA'))
    params.set('last', String(recent.length))
    get<MatchRow[]>('matches', params.toString()).then((found) => current && (before = found), () => {})
    return () => (current = false)
  })
  // the same matches over every role, for the role wheel to turn from all roles to the picked ones; the main fetch reports errors
  let everyRole = $state.raw<MatchRow[]>([])
  const roleless = $derived(new URLSearchParams([...new URLSearchParams(query)].filter(([k]) => k !== 'position')).toString())
  $effect(() => {
    let current = true
    get<MatchRow[]>('matches', roleless).then((found) => current && (everyRole = found), () => {})
    return () => (current = false)
  })

  const TOP_HEROES = 10
  const LANES = 5 // matches in the best and in the worst lanes
  const EVEN = 500 // a lane within this much net worth at 10:00 counts as even
  const wins = $derived(recent.filter((r) => r.win).length)
  const share = (part: number) => `${percent(part, recent.length)}%`
  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString('en-GB', { dateStyle: 'medium' })

  const heroes = $derived(tally(recent))
  const roles = $derived(recent.map((r) => ({ ...r, role: r.position })))
  const allRoles = $derived(everyRole.map((r) => ({ ...r, role: r.position })))
  const FORM = 15 // results in the Form card
  let heroOpen = $state(0) // the hero a click in the Overview's table opens on the Heroes tab
  const form = $derived(recent.slice(0, FORM).reverse())
  const formWins = $derived(form.filter((r) => r.win).length)

  const signed = (n: number) => `${n > 0 ? '+' : ''}${Math.round(n).toLocaleString()}`
  const note = (r: MatchRow) =>
    `${heroName(r.hero_id)}, ${date(r.start_time)}: ${r.win ? 'won' : 'lost'}` +
    (r.lane_nw_diff === null ? '' : `, lane ${signed(r.lane_nw_diff)} net worth at 10:00`)

  const parsed = $derived(recent.filter((r) => r.replay_state === 'parsed').length)
  const kda = $derived([mean(recent.map((r) => r.kills)), mean(recent.map((r) => r.deaths)), mean(recent.map((r) => r.assists))])
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

  // ---- general: averages over the matches shown, sorted into sections, each with its spread and its trend
  const FEW = 10 // a stat over fewer matches than this is dimmed as rough, and gets no trend
  /** One number of a cell: `sum` counts instead of averaging; `replay` stats are null without a parsed replay */
  type Part = { of: (r: MatchRow) => number | null; show: (v: number) => string; name?: string; sum?: true; replay?: true }
  /** `better` 1 when more is better, -1 when less is; neither gets no colour. `spread` false: no median or best game */
  type Cell = { label: string; parts: Part[]; better?: 1 | -1; signed?: true; spread?: false }
  const one = (v: number) => v.toFixed(1)
  const whole = (v: number) => Math.round(v).toLocaleString()
  const pct = (v: number) => `${Math.round(100 * v)}%`
  const lead = (digits: number) => (v: number) => {
    const t = Math.abs(v).toFixed(digits)
    return Number(t) === 0 ? t : `${v > 0 ? '+' : '−'}${t}`
  }
  const stat = (key: keyof MatchRow, show = one): Part => ({ of: (r) => r[key] as number | null, show })
  const replay = (key: keyof MatchRow, show = one, name?: string): Part => ({ ...stat(key, show), replay: true, name })
  const SECTIONS: [string, Cell[]][] = [
    ['Results', [
      { label: 'Matches', parts: [{ of: () => 1, show: String, sum: true }], spread: false },
      { label: 'Win rate', parts: [stat('win', pct)], better: 1, spread: false },
      { label: 'Parsed matches', parts: [{ of: (r) => +(r.replay_state === 'parsed'), show: String, sum: true }], spread: false },
    ]],
    ['Combat', [
      { label: 'Kills', parts: [stat('kills')], better: 1 },
      { label: 'Deaths', parts: [stat('deaths')], better: -1 },
      { label: 'Assists', parts: [stat('assists')], better: 1 },
    ]],
    ['Economy', [
      { label: 'Gold per minute', parts: [stat('gold_per_min', whole)], better: 1 },
      { label: 'Experience per minute', parts: [stat('xp_per_min', whole)], better: 1 },
      { label: 'Camps stacked', parts: [replay('camps_stacked')] },
    ]],
    ['Laning at 10:00, vs the enemy lane', [
      { label: 'Last hits', parts: [replay('lane_cs_diff', lead(1))], better: 1, signed: true },
      { label: 'Net worth', parts: [replay('lane_nw_diff', lead(0))], better: 1, signed: true },
      { label: 'Denies', parts: [replay('lane_dn_diff', lead(1))], better: 1, signed: true },
    ]],
    ['Fights', [
      { label: 'Kill participation', parts: [replay('kill_participation', pct)], better: 1 },
      { label: 'Teamfights taken part in', parts: [replay('fight_participation', pct)], better: 1 },
      { label: 'Deaths outside teamfights', parts: [replay('deaths_outside_fights')], better: -1 },
    ]],
    ['Vision', [
      { label: 'Observers placed / bought', parts: [replay('obs_placed', one, 'placed'), replay('obs_bought', one, 'bought')] },
      { label: 'Sentries placed / bought', parts: [replay('sen_placed', one, 'placed'), replay('sen_bought', one, 'bought')] },
      { label: 'Enemy wards destroyed', parts: [replay('wards_destroyed')], better: 1 },
      { label: 'Observer lifetime', parts: [replay('obs_lifetime', (v) => clock(Math.round(v)))], better: 1 },
    ]],
  ] // prettier-ignore

  /** A part over some matches: its average (or sum), median, lowest and highest, and how many matches have it */
  function summary(rows: MatchRow[], part: Part) {
    const v = rows.map(part.of).filter((x) => x !== null).sort((a, b) => a - b)
    const total = v.reduce((a, b) => a + b, 0)
    if (!v.length) return null
    const median = v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2
    return { value: part.sum ? total : total / v.length, median, low: v[0], high: v.at(-1)!, n: v.length }
  }
  /** What a cell shows: the value, a ▲/▼ against the matches before (on its first part), and the hover text */
  function describe(cell: Cell) {
    const now = cell.parts.map((p) => summary(recent, p))
    const n = Math.min(...now.map((s) => s?.n ?? 0))
    const rough = n > 0 && n < FEW && !cell.parts[0].sum
    const lines = rough ? [`Only ${n} parsed matches have this, so it is a rough number.`] : []
    cell.parts.forEach((p, i) => {
      const s = now[i]
      if (!s || p.sum) return
      const of = `${p.name ? `${p.name[0].toUpperCase()}${p.name.slice(1)}: a` : 'A'}verage over ${s.n} ${p.replay ? 'parsed ' : ''}matches`
      const [best, worst] = cell.better === -1 ? [s.low, s.high] : [s.high, s.low]
      const words = cell.better ? ['best game', 'worst'] : ['most in a game', 'fewest']
      const game = (x: number) => p.show(x).replace(/\.0$/, '') // single games are whole counts
      const spread = cell.spread === false ? '' : `; median ${game(s.median)}, ${words[0]} ${game(best)}, ${words[1]} ${game(worst)}`
      lines.push(of + spread)
    })
    let trend: { up: boolean; text: string; tone: string } | null = null
    const [part, s] = [cell.parts[0], now[0]]
    const was = before.length >= FEW && !part.sum ? summary(before, part) : null
    if (s && was && was.n >= FEW && !rough) {
      lines.push(`The ${before.length} matches before these: ${cell.parts.map((p) => summary(before, p)).map((w, i) => (w ? cell.parts[i].show(w.value) : '–')).join(' / ')}`)
      const delta = s.value - was.value
      if (part.show(s.value) !== part.show(was.value)) {
        const text = part.show(Math.abs(delta)).replace(/^[+−]/, '')
        trend = { up: delta > 0, text, tone: !cell.better ? '' : delta * cell.better > 0 ? 'good' : 'bad' }
      }
    }
    const value = now.map((x, i) => (x ? cell.parts[i].show(x.value) : '–')).join(' / ')
    const tone = cell.signed && s ? (s.value > 0 ? 'good' : s.value < 0 ? 'bad' : '') : ''
    return { value, tone, rough, trend, title: lines.join('\n') }
  }
  const general = $derived(SECTIONS.map(([title, cells]) => [title, cells.map((c) => [c, describe(c)] as const)] as const))

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
  const laning = $derived([
    ['By 10:00', [
      ['Last hits', at10('last_hits_at_10'), 'creeps and neutrals', ''],
      ['Denies', at10('denies_at_10'), '', ''],
      ['Net worth', at10('net_worth_at_10'), '', ''],
      ['Experience', at10('xp_at_10'), '', ''],
      ['Kills', at10('kills_by_10'), '', 'tenths'],
      ['Deaths', at10('deaths_by_10'), '', 'tenths'],
      ['Camps pulled', at10('camps_pulled_by_10'), '', 'tenths'],
      ['Damage dealt', at10('damage_at_10'), 'to enemy heroes', ''],
      ['Damage taken', at10('damage_taken_at_10'), 'from enemy heroes', ''],
    ]],
    ['Your lane vs the enemy lane, by 10:00', [
      ['Net worth lead', at10('lane_nw_diff'), 'your lane minus theirs', 'signed'],
      ['Last-hit lead', at10('lane_cs_diff'), 'your lane minus theirs', 'signed'],
      ['Deny lead', at10('lane_dn_diff'), 'your lane minus theirs', 'signed'],
      ['Your lane dealt', at10('lane_damage_at_10'), 'you and your lane partner, to enemy heroes', ''],
      ['Enemy lane dealt', at10('enemy_lane_damage_at_10'), 'the heroes you laned against, to your side', ''],
    ]],
  ] as const) // prettier-ignore
  // the matches with the biggest and smallest net worth lead; with few matches each list takes its half, so none is in both
  const extremes = $derived.by(() => {
    const ranked = laneGames.filter((r) => r.lane_nw_diff !== null).sort((a, b) => b.lane_nw_diff! - a.lane_nw_diff!)
    const best = ranked.slice(0, Math.min(LANES, Math.ceil(ranked.length / 2)))
    return [['Best lanes', best], ['Worst lanes', ranked.slice(best.length).reverse().slice(0, LANES)]] as const
  })
  const shownStat = (value: number | null, kind: string) =>
    value === null ? '–' : kind === 'signed' ? signed(value) : kind === 'tenths' ? value.toFixed(1) : Math.round(value).toLocaleString()

  // ---- activity: games per day over the last 6 months, one column per week from Monday
  const dayOf = (d: Date) => d.toLocaleDateString('en-CA')
  const perDay = $derived(
    recent.reduce((m, r) => {
      const key = dayOf(new Date(r.start_time * 1000))
      const day = m.get(key) ?? { games: 0, wins: 0 }
      return m.set(key, { games: day.games + 1, wins: day.wins + r.win })
    }, new Map<string, { games: number; wins: number }>()),
  )
  /** Keeps a scrolled calendar at its newest end whenever its size changes: first layout, a phone turned. */
  function toNewest(el: HTMLElement) {
    const watch = new ResizeObserver(() => (el.scrollLeft = el.scrollWidth))
    watch.observe(el)
    return () => watch.disconnect()
  }
  const weeks = $derived.by(() => {
    const day = new Date()
    day.setHours(0, 0, 0, 0)
    day.setMonth(day.getMonth() - 6)
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
  const dot = (games: number) => `${games && Math.max(30, 81 * Math.sqrt(games / busiest))}%` // of the day's square
  const dayNote = (d: { date: Date; games: number; wins: number }) =>
    `${d.date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}: ${d.games || 'no'} ${d.games === 1 ? 'game' : 'games'}` +
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
      <button role="tab" aria-selected={shown === id} onclick={() => ((heroOpen = 0), (location.hash = id === 'overview' ? 'profile' : `profile/${id}`))}>{title}</button>
    {/each}
  </div>

  {#if shown === 'matches'}
    <Matches {query} />
  {:else if shown === 'heroes'}
    <Heroes {query} matches={recent} open={heroOpen} />
  {:else if shown === 'teammates'}
    <Teammates {query} />
  {:else if shown === 'overview'}
  <dl class="card numbers">
    <div>
      <dt>Win rate</dt>
      <dd>{share(wins)}</dd>
    </div>
    <div title="Even is within {EVEN} net worth at 10:00">
      <dt>Lanes won, even, lost</dt>
      <dd><span class="good">{lanes.won}</span> – {lanes.even} – <span class="bad">{lanes.lost}</span></dd>
    </div>
    <div>
      <dt>K / D / A</dt>
      {#if kda.every((v) => v !== null)}
        {@const [k, d, a] = kda as number[]}
        <dd>{k.toFixed(1)} / {d.toFixed(1)} / {a.toFixed(1)}</dd>
      {:else}
        <dd>–</dd>
      {/if}
    </div>
    <div>
      <dt>With tracked players</dt>
      <dd>{share(recent.filter((r) => r.with_tracked).length)}</dd>
    </div>
  </dl>
  <div class="overview">
    <section class="card roles">
      <RoleWheel games={allRoles} zoomed={roles} picked={positions} onpick={(p) => onpositions(p as typeof positions)} none="No replay" />
    </section>

    <section class="card">
      <table>
        <thead>
          <tr><th>Hero</th><th>Matches</th><th>Win rate</th><th class="num">K / D / A</th></tr>
        </thead>
        <tbody>
          {#each heroes.slice(0, TOP_HEROES) as h (h.hero_id)}
            <tr class="open" onclick={() => ((heroOpen = h.hero_id), (location.hash = 'profile/heroes'))}>
              <td>
                <a href="#profile/heroes" onclick={() => (heroOpen = h.hero_id)} aria-label="{heroName(h.hero_id)} on the Heroes tab">
                  <img class="icon" src={heroPortrait(h.hero_id)} alt={heroName(h.hero_id)} title={heroName(h.hero_id)} width="44" height="25" loading="lazy" />
                </a>
              </td>
              <td><Count games={h.games} max={heroes[0].games} /></td>
              <td><WinRate wins={h.wins} games={h.games} /></td>
              <td class="num">{(h.kills / h.games).toFixed(1)} / {(h.deaths / h.games).toFixed(1)} / {(h.assists / h.games).toFixed(1)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  </div>

  <div class="lower">
  <section class="card activity">
    <h3>Activity</h3>
    <!-- too wide for a phone: it scrolls, and opens at its newest end -->
    <div class="calendar" {@attach toNewest} style:--weeks={weeks.length} role="img" aria-label="Games and win rate per day over the last 6 months: {active.length} days played">
      <div class="week">
        <span class="month"></span>
        {#each weeks[0] as d, i}<span class="weekday">{i % 2 ? '' : d.date.toLocaleDateString('en-GB', { weekday: 'short' })}</span>{/each}
      </div>
      {#each weeks as week, w}
        {@const first = week.find((d) => d.date.getDate() === 1)}
        <div class="week" style:--w={w}>
          <span class="month">{first ? first.date.toLocaleDateString('en-GB', { month: 'short' }) : ''}</span>
          {#each week as d}
            <i title={dayNote(d)}><b style:background={d.games ? tint(d) : 'transparent'} style:width={dot(d.games)}></b></i>
          {/each}
        </div>
      {/each}
    </div>
    <p class="muted">{active.reduce((n, d) => n + d.games, 0)} games on {active.length} days in the last 6 months, at most {busiest} in one day.</p>
  </section>
  <section class="card results">
    <h3>Form <span class="tally"><b class="won">{formWins} W</b> <b class="lost">{form.length - formWins} L</b></span></h3>
    <ol aria-label="The last {form.length} results, oldest first">
      {#each form as r (r.match_id)}
        <li><a href="#match/{r.match_id}" title={note(r)}>
          <img src={heroIcon(r.hero_id)} alt={note(r)} width="32" height="32" />
          <span class="mark" class:won={r.win} aria-hidden="true">{r.win ? 'W' : 'L'}</span>
        </a></li>
      {/each}
    </ol>
  </section>
  </div>

  {:else if shown === 'general'}
  <div class="sections">
    {#each general as [title, cells] (title)}
      <section class="card">
        <h3>{title}</h3>
        <dl class="numbers">
          {#each cells as [cell, d] (cell.label)}
            <div class:rough={d.rough} title={d.title}>
              <dt>{cell.label}</dt>
              <dd class={d.tone}>
                {d.value}
                <span class="trend {d.trend?.tone}">{d.trend ? `${d.trend.up ? '▲' : '▼'} ${d.trend.text}` : ''}</span>
              </dd>
            </div>
          {/each}
        </dl>
      </section>
    {/each}
  </div>

  {:else if shown === 'laning'}
  <p class="muted laning">All numbers are your averages at 10:00 over the {laneMatches} filtered matches{onHero ? ` on ${heroName(laneHero)}` : ''} with a parsed replay.<About>Averages over the {laneMatches} of these {laneGames.length} matches{onHero ? ` on ${heroName(laneHero)}` : ''} that have a parsed replay and lasted 10 minutes. Your lane is you and the allies who laned with you, the enemy lane the heroes you laned against; in the mid lane that is usually one hero each. Damage counts only hits on heroes, after armour and resistances, as the replay's combat log records it. The best and worst lanes are the {LANES} of these matches with the biggest and the smallest net worth lead at 10:00, each with every hero of both lanes, yours first; click a date to open the match.</About></p>
  <label class="pick">
    Hero
    <select value={onHero ? laneHero : 0} onchange={(e) => (laneHero = +e.currentTarget.value)}>
      <option value={0}>All heroes ({recent.length})</option>
      {#each heroes as h (h.hero_id)}<option value={h.hero_id}>{heroName(h.hero_id)} ({h.games})</option>{/each}
    </select>
  </label>
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
      <!-- the scale: built like a column, so its labels line up with the bars -->
      <span class="scale" aria-hidden="true">
        <b></b>
        <span class="lane"><small>+{(reach / 1000).toFixed(1)}k</small><small>0</small><small>−{(reach / 1000).toFixed(1)}k</small></span>
      </span>
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
    <p class="muted">Lane net worth lead at 10:00, one column per match.<About>One column per match, the oldest on the left. The bar is the net worth lead of the player's lane at 10:00: up when ahead, down when behind. A match without a parsed replay has no bar. The dot is the result.</About></p>
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
              {@const nw = r.lane_nw_diff}
              {@const cs = r.lane_cs_diff}
              <tr>
                <td><a href="#match/{r.match_id}">{date(r.start_time)}</a></td>
                <!-- the whole lane on both sides: you first, then your lane partners -->
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
    grid-template-columns: minmax(300px, 9fr) minmax(0, 11fr);
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
  tr.open {
    cursor: pointer;
  }
  tr.open:hover {
    background: var(--raised);
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
  .scale {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 4px 6px 0 0;
  }
  .scale b {
    height: 22px;
  }
  .strip.dense .scale b {
    display: none;
  }
  .scale .lane {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    align-items: flex-end;
    background: none;
    font-size: 11px;
    line-height: 1;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  /* the labels' middles on the top, the middle line and the bottom of the bars */
  .scale small:first-child {
    margin-top: -5px;
  }
  .scale small:last-child {
    margin-bottom: -5px;
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

  /* the activity under the wheel and as wide, the form beside it under the heroes */
  .lower {
    display: grid;
    grid-template-columns: minmax(300px, 9fr) minmax(0, 11fr);
    gap: 12px;
    margin-bottom: 12px;
  }
  @media (max-width: 900px) {
    .lower {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  .activity,
  .results {
    padding: 14px 18px;
  }
  .lower h3 {
    margin: 0 0 8px;
  }
  .lower p {
    margin: 8px 0 0;
    font-size: 13px;
  }
  .activity {
    min-width: 0;
    container-type: inline-size;
  }
  /* a day's cell shares the card's width with the others (16 px at most); below 7 px the calendar scrolls instead.
     Rows are taller than the cells are wide, so the 6 months fill more of the card's height */
  .calendar {
    --cell: max(7px, min(16px, (100cqi - 33px) / var(--weeks) - 3px));
    --row: calc(var(--cell) * 1.45);
    overflow-x: auto;
    padding-bottom: 4px; /* room for the last weekday label when rows are thinner than its text */
    display: flex;
    gap: 3px;
  }
  .week {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .month {
    width: var(--cell); /* the name runs over into the next weeks */
    height: 18px;
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }
  /* every second day named: a label taller than its row spills into the unnamed one */
  .weekday {
    display: grid;
    align-items: center;
    width: 30px;
    height: var(--row);
    font-size: 11px;
    color: var(--muted);
  }
  .week i {
    display: grid;
    place-items: center;
    width: var(--cell);
    height: var(--row);
    background: var(--raised);
    border-radius: 3px;
  }
  /* a change of filters grows, shrinks and recolours the circles, one week after the other from the left */
  .week b {
    aspect-ratio: 1;
    border-radius: 50%;
    transition-property: width, background-color;
    transition-duration: 0.45s;
    transition-timing-function: cubic-bezier(0.65, 0, 0.35, 1);
    transition-delay: calc(var(--w) * 12ms);
  }
  @media (prefers-reduced-motion: reduce) {
    .week b {
      transition: none;
    }
  }
  .tally {
    margin-left: 10px;
    font-size: 15px;
  }
  .tally .won {
    color: var(--radiant);
  }
  .tally .lost {
    margin-left: 6px;
    color: var(--dire);
  }
  /* one row of heroes, a W or L disc under each: green won, red lost; the row sits in the middle of the card's height */
  .results {
    display: flex;
    flex-direction: column;
  }
  .results ol {
    display: grid;
    grid-template-columns: repeat(15, minmax(0, 48px));
    gap: 5px;
    margin: auto 0;
    padding: 0;
    list-style: none;
  }
  .results a {
    display: grid;
    justify-items: center;
    gap: 7px;
    text-decoration: none;
  }
  .results a:hover {
    filter: brightness(1.2);
  }
  .results img {
    display: block;
    width: 100%;
    height: auto;
    border-radius: 3px;
  }
  .mark {
    display: grid;
    place-items: center;
    width: min(24px, 100%);
    aspect-ratio: 1;
    border-radius: 50%;
    font-size: 12px;
    font-weight: 800;
    color: #fff;
    background: var(--dire);
  }
  .mark.won {
    background: var(--radiant);
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
  .sections {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
    gap: 12px;
  }
  .sections section {
    padding: 14px 4px 4px;
  }
  .sections h3 {
    margin: 0 14px 4px;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-2);
  }
  .sections .numbers {
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    margin: 0;
  }
  .sections .numbers div {
    display: flex;
    flex-direction: column;
    padding: 8px 14px 12px;
    border: 0;
  }
  /* labels of one or two lines: the numbers of a row still line up at the bottom */
  .sections dt {
    flex: 1;
    font-size: 13px;
  }
  .sections dt + dd {
    font-size: 24px;
    white-space: nowrap;
  }
  .rough {
    opacity: 0.5;
  }
  .trend {
    display: block;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.2;
    min-height: 1.2em;
    color: var(--muted);
  }
  .trend.good {
    color: var(--good);
  }
  .trend.bad {
    color: var(--critical);
  }
</style>
