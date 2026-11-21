<script module lang="ts">
  import { percent } from './api'

  /** A lane (team pages) or a position 1–5 (profile) */
  export type Role = 'safe' | 'mid' | 'off' | 'jungle' | 'none' | 1 | 2 | 3 | 4 | 5
  export type Game = { hero_id: number; win: number | boolean; role: Role; kills: number | null; deaths: number | null; assists: number | null }
  export type Tally = { hero_id: number; games: number; wins: number; kills: number; deaths: number; assists: number }

  /** Games per hero, most played first. */
  export function tally(games: Omit<Game, 'role'>[]): Tally[] {
    const found = new Map<number, Tally>()
    for (const g of games) {
      const t = found.get(g.hero_id) ?? { hero_id: g.hero_id, games: 0, wins: 0, kills: 0, deaths: 0, assists: 0 }
      found.set(g.hero_id, {
        ...t,
        games: t.games + 1,
        wins: t.wins + Number(g.win),
        kills: t.kills + (g.kills ?? 0),
        deaths: t.deaths + (g.deaths ?? 0),
        assists: t.assists + (g.assists ?? 0),
      })
    }
    return [...found.values()].sort((a, b) => b.games - a.games || b.wins - a.wins)
  }

  const record = (wins: number, games: number) => `${games} ${games === 1 ? 'match' : 'matches'}, ${percent(wins, games)}% won`
</script>

<script lang="ts">
  import { cubicInOut } from 'svelte/easing'
  import { prefersReducedMotion, Tween } from 'svelte/motion'
  import { heroIcon, heroName } from './constants.svelte'

  /** `none` names the games without a known lane. */
  let { games, none }: { games: Game[]; none: string } = $props()

  const ROLES = new Map<Role, { title: string; color: string }>([
    [1, { title: 'Pos 1 (carry)', color: 'series-1' }],
    [2, { title: 'Pos 2 (mid)', color: 'series-2' }],
    [3, { title: 'Pos 3 (offlane)', color: 'series-4' }],
    [4, { title: 'Pos 4 (soft support)', color: 'series-3' }],
    [5, { title: 'Pos 5 (hard support)', color: 'series-5' }],
    ['safe', { title: 'Safe lane', color: 'series-1' }],
    ['mid', { title: 'Mid lane', color: 'series-2' }],
    ['off', { title: 'Off lane', color: 'series-4' }],
    ['jungle', { title: 'Jungle', color: 'series-3' }],
    ['none', { title: none, color: 'axis' }],
  ])
  /** Each role's share of the games, and inside it the heroes played there. `from` and `to` are turns. */
  const wheel = $derived.by(() => {
    let at = 0
    return [...ROLES.keys()].flatMap((id) => {
      const mine = games.filter((g) => g.role === id)
      if (!mine.length) return []
      const from = at
      const slices = tally(mine).map((t) => ({ ...t, from: at, to: (at += t.games / games.length) }))
      return [{ id, ...ROLES.get(id)!, games: mine.length, wins: mine.filter((g) => g.win).length, from, to: at, slices }]
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

  // ---- a lane clicked in the middle ring fills the whole wheel: 0 shows all lanes, 1 that lane alone
  let focus = $state<Role>() // kept while the wheel widens back, so it unfolds the way it folded
  const zoom = new Tween(0, { easing: cubicInOut })
  const show = (id?: Role) => {
    if (id) focus = id
    zoom.set(id ? 1 : 0, { duration: prefersReducedMotion.current ? 0 : 700 })
  }
  const alone = $derived(zoom.target === 1 ? wheel.find((r) => r.id === focus) : undefined)
  /** Where a turn of the full wheel is drawn: `zoom` of the way to its place once the focused lane fills the ring. */
  function turn(t: number) {
    const r = wheel.find((r) => r.id === focus)
    if (!r) return t
    return t + zoom.current * (Math.min(1, Math.max(0, (t - r.from) / (r.to - r.from))) - t)
  }
</script>

<div class="roles">
  <svg viewBox="-100 -100 200 200" role="group" aria-label="Roles and heroes of the last {games.length} matches; click a part of the middle ring to see it alone; the lists beside it have the numbers">
    {#each wheel as role (role.id)}
      <path
        class="role"
        class:pick={!alone}
        d={segment(36, 56, turn(role.from), turn(role.to))}
        style:fill="var(--{role.color})"
        role="button"
        tabindex={alone ? -1 : 0}
        onclick={() => !alone && show(role.id)}
        onkeydown={(e) => !alone && (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), show(role.id))}
      >
        <title>{role.title}: {record(role.wins, role.games)}</title>
      </path>
      {#each role.slices as s (s.hero_id)}
        {@const from = turn(s.from)}
        {@const to = turn(s.to)}
        {@const middle = (from + to) / 2}
        <g class="slice">
          <title>{heroName(s.hero_id)}, {role.title.toLowerCase()}: {record(s.wins, s.games)}</title>
          <path d={segment(59, 97, from, to)} class:winning={s.wins * 2 >= s.games} class:losing={s.wins * 2 < s.games} />
          {#if (to - from) * 2 * Math.PI * ICON_AT >= ICON + 2}
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
    <text class="count" y="2">{alone ? alone.games : games.length}</text>
    <text class="unit" y="15">{alone ? alone.title.toLowerCase() : 'matches'}</text>
  </svg>
  <ul>
    {#each wheel as role (role.id)}
      <li>
        <i class="swatch" style:background="var(--{role.color})"></i>{role.title}
        <span class="muted">{record(role.wins, role.games)}</span>
      </li>
    {/each}
    <li class="muted key">
      Outer ring: the heroes played there, green when winning at least half, red when losing more. Click a part of the
      middle ring to see its heroes alone.
    </li>
    {#if alone}<li><button class="action" onclick={() => show()}>Show all</button></li>{/if}
  </ul>
</div>

<style>
  .roles {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 12px 24px;
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
  .role.pick {
    cursor: pointer;
  }
  .role.pick:hover {
    filter: brightness(1.2);
  }
  .role:focus-visible {
    outline: none;
    stroke: var(--text);
  }
  /* a hero's slice is tinted by its win rate: green from half up, red below */
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
  ul {
    flex: 0 1 170px;
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 8px;
  }
  li .muted {
    display: block;
    padding-left: 16px;
    font-size: 13px;
  }
  .key {
    max-width: 24ch;
    font-size: 13px;
  }
</style>
