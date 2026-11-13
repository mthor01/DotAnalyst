<script lang="ts">
  import { get, percent, type Account, type MatchRow } from './lib/api'
  import { heroIcon, heroName } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'

  let { query, account }: { query: string; account: Account | undefined } = $props()
  let rows = $state<MatchRow[]>([])
  let error = $state('')
  let size = $state(25)

  $effect(() => {
    let current = true
    get<MatchRow[]>('matches', query).then(
      (found) => current && ((rows = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const SIZES = [25, 100]
  const TOP_HEROES = 10
  const EVEN = 500 // a lane within this much net worth at 10:00 counts as even
  const recent = $derived(rows.slice(0, size)) // the API returns newest first
  const wins = $derived(recent.filter((r) => r.win).length)
  const share = (part: number) => `${percent(part, recent.length)}%`
  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString(undefined, { dateStyle: 'medium' })

  // ---- roles: the lane seen from the player's side. Radiant's safe lane is bottom, Dire's is top.
  const ROLES = {
    safe: { title: 'Safe lane', color: 'series-1' },
    mid: { title: 'Mid lane', color: 'series-2' },
    off: { title: 'Off lane', color: 'series-4' },
    jungle: { title: 'Jungle', color: 'series-3' },
    none: { title: 'No replay', color: 'axis' },
  }
  type Role = keyof typeof ROLES
  function roleOf(r: MatchRow): Role {
    if (r.lane === 'top' || r.lane === 'bot') return (r.lane === 'bot') === r.radiant ? 'safe' : 'off'
    return r.lane ?? 'none'
  }
  type Tally = { hero_id: number; games: number; wins: number; kills: number; deaths: number; assists: number }
  /** Games per hero, most played first. */
  function tally(matches: MatchRow[]): Tally[] {
    const found = new Map<number, Tally>()
    for (const r of matches) {
      const t = found.get(r.hero_id) ?? { hero_id: r.hero_id, games: 0, wins: 0, kills: 0, deaths: 0, assists: 0 }
      found.set(r.hero_id, { ...t, games: t.games + 1, wins: t.wins + r.win, kills: t.kills + r.kills, deaths: t.deaths + r.deaths, assists: t.assists + r.assists })
    }
    return [...found.values()].sort((a, b) => b.games - a.games || b.wins - a.wins)
  }
  const heroes = $derived(tally(recent))
  /** The wheel: each role's share of the matches, and inside it the heroes played there. `from` and `to` are turns. */
  const wheel = $derived.by(() => {
    let at = 0
    return (Object.keys(ROLES) as Role[]).flatMap((id) => {
      const mine = recent.filter((r) => roleOf(r) === id)
      if (!mine.length) return []
      const from = at
      const slices = tally(mine).map((t) => ({ ...t, from: at, to: (at += t.games / recent.length) }))
      return [{ id, ...ROLES[id], games: mine.length, wins: mine.filter((r) => r.win).length, from, to: at, slices }]
    })
  })
  const point = (r: number, turn: number) => `${r * Math.sin(2 * Math.PI * turn)} ${-r * Math.cos(2 * Math.PI * turn)}`
  /** A ring segment between two radii, clockwise from the top. */
  function segment(inner: number, outer: number, from: number, to: number): string {
    to = Math.min(to, from + 0.9999) // a full circle has no direction to draw in
    const large = to - from > 0.5 ? 1 : 0
    return `M${point(outer, from)}A${outer} ${outer} 0 ${large} 1 ${point(outer, to)}L${point(inner, to)}A${inner} ${inner} 0 ${large} 0 ${point(inner, from)}Z`
  }
  const ICON = 15 // in the wheel's units; a slice shorter than this along its arc gets no hero icon
  const ICON_AT = 78
  const record = (wins: number, games: number) => `${games} ${games === 1 ? 'match' : 'matches'}, ${percent(wins, games)}% won`

  // ---- the strip: one column per match, oldest on the left
  const strip = $derived([...recent].reverse())
  const reach = $derived(Math.max(1000, ...recent.map((r) => Math.abs(r.lane_nw_diff ?? 0))))
  const signed = (n: number) => `${n > 0 ? '+' : ''}${Math.round(n).toLocaleString()}`
  const note = (r: MatchRow) =>
    `${heroName(r.hero_id)}, ${date(r.start_time)}: ${r.win ? 'won' : 'lost'}` +
    (r.lane_nw_diff === null ? '' : `, lane ${signed(r.lane_nw_diff)} net worth at 10:00`)

  const laned = $derived(recent.filter((r) => r.lane_nw_diff !== null))
  const lanes = $derived({
    won: laned.filter((r) => r.lane_nw_diff! > EVEN).length,
    even: laned.filter((r) => Math.abs(r.lane_nw_diff!) <= EVEN).length,
    lost: laned.filter((r) => r.lane_nw_diff! < -EVEN).length,
  })
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if rows.length === 0}
  <p class="muted">No matches for these filters.</p>
{:else}
  <header class="title">
    <h2>{account?.label ?? account?.account_id}</h2>
    <p class="muted">The last {recent.length} of {rows.length} matches for these filters</p>
    <div class="sizes" role="group" aria-label="How many matches">
      {#each SIZES as n}
        <button aria-pressed={size === n} onclick={() => (size = n)}>{n} matches</button>
      {/each}
    </div>
  </header>

  <div class="overview">
    <section class="card roles">
      <svg viewBox="-100 -100 200 200" role="img" aria-label="Roles and heroes of the last {recent.length} matches; the lists beside it have the numbers">
        {#each wheel as role (role.id)}
          <path class="role" d={segment(36, 56, role.from, role.to)} style:fill="var(--{role.color})">
            <title>{role.title}: {record(role.wins, role.games)}</title>
          </path>
          {#each role.slices as s (s.hero_id)}
            {@const middle = (s.from + s.to) / 2}
            <g class="slice">
              <title>{heroName(s.hero_id)}, {role.title.toLowerCase()}: {record(s.wins, s.games)}</title>
              <path d={segment(59, 97, s.from, s.to)} class:winning={s.wins * 2 > s.games} class:losing={s.wins * 2 < s.games} />
              {#if (s.to - s.from) * 2 * Math.PI * ICON_AT >= ICON + 2}
                <image
                  href={heroIcon(s.hero_id)}
                  x={ICON_AT * Math.sin(2 * Math.PI * middle) - ICON / 2}
                  y={-ICON_AT * Math.cos(2 * Math.PI * middle) - ICON / 2}
                  width={ICON}
                  height={ICON}
                />
              {/if}
            </g>
          {/each}
        {/each}
        <text class="count" y="2">{recent.length}</text>
        <text class="unit" y="15">matches</text>
      </svg>
      <ul>
        {#each wheel as role (role.id)}
          <li>
            <i class="swatch" style:background="var(--{role.color})"></i>{role.title}
            <span class="muted">{record(role.wins, role.games)}</span>
          </li>
        {/each}
        <li class="muted key">Outer ring: the heroes played there, green when winning more than half, red when losing more.</li>
      </ul>
    </section>

    <section class="card">
      <table>
        <thead>
          <tr><th>Hero</th><th class="num">Matches</th><th>Win rate</th><th class="num">K / D / A</th></tr>
        </thead>
        <tbody>
          {#each heroes.slice(0, TOP_HEROES) as h (h.hero_id)}
            <tr>
              <td><Hero id={h.hero_id} /></td>
              <td class="num">{h.games}</td>
              <td>
                <span class="rate" class:losing={h.wins * 2 < h.games}><i style:width="{percent(h.wins, h.games)}%"></i></span>
                {percent(h.wins, h.games)}%
              </td>
              <td class="num">{(h.kills / h.games).toFixed(1)} / {(h.deaths / h.games).toFixed(1)} / {(h.assists / h.games).toFixed(1)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if heroes.length > TOP_HEROES}
        <p class="muted more">The {TOP_HEROES} most played of {heroes.length} heroes. The Heroes page has them all.</p>
      {/if}
    </section>
  </div>

  <section class="card form">
    <div class="strip" class:dense={size > 25}>
      {#each strip as r (r.match_id)}
        {@const lead = r.lane_nw_diff}
        <a href="#match/{r.match_id}" title={note(r)} aria-label={note(r)}>
          <img src={heroIcon(r.hero_id)} alt="" width="22" height="22" loading="lazy" />
          <span class="lane">
            {#if lead !== null}
              <i class={lead < 0 ? 'behind' : 'ahead'} style:height="{Math.max(2, (50 * Math.abs(lead)) / reach)}%"></i>
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
  .title p {
    margin: 0;
  }
  .sizes {
    margin-left: auto;
    display: flex;
    background: var(--surface);
    border-radius: 4px;
    padding: 2px;
  }
  .sizes button {
    font: inherit;
    font-weight: 600;
    color: var(--muted);
    background: none;
    border: 0;
    border-radius: 3px;
    padding: 4px 12px;
    cursor: pointer;
  }
  .sizes button[aria-pressed='true'] {
    background: var(--raised);
    color: var(--text);
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
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 12px 24px;
    padding: 18px;
  }
  .roles svg {
    flex: 0 1 270px;
    min-width: 200px;
  }
  .role,
  .slice path {
    stroke: var(--surface);
    stroke-width: 1.2;
  }
  /* a hero's slice is tinted by its win rate: green above half, red below, plain at exactly half */
  .slice path {
    fill: var(--muted);
    fill-opacity: 0.25;
  }
  .slice .winning {
    fill: var(--good);
  }
  .slice .losing {
    fill: var(--critical);
  }
  .slice:hover path {
    fill-opacity: 0.5;
  }
  .slice image {
    pointer-events: none;
  }
  text {
    text-anchor: middle;
    fill: var(--text);
  }
  .count {
    font-size: 22px;
    font-weight: 800;
    font-stretch: 125%;
  }
  .unit {
    font-size: 8px;
    fill: var(--muted);
  }
  .roles ul {
    flex: 0 1 170px;
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 8px;
  }
  .roles li .muted {
    display: block;
    padding-left: 16px;
    font-size: 13px;
  }
  .roles .key {
    max-width: 24ch;
    font-size: 13px;
  }
  .rate {
    display: inline-block;
    width: 90px;
    height: 6px;
    margin-right: 8px;
    border-radius: 2px;
    background: var(--raised);
    vertical-align: 1px;
    overflow: hidden;
  }
  .rate i {
    display: block;
    height: 100%;
    background: var(--good);
  }
  .rate.losing i {
    background: var(--critical);
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

  .numbers {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    margin: 0;
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
