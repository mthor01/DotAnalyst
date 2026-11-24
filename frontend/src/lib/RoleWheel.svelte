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
  import { untrack } from 'svelte'
  import { heroIcon, heroName } from './constants.svelte'

  /** `none` names the games without a known lane. With `onpick` the roles shown alone are kept outside, as `picked`: a click
   *  in the middle ring asks for them and the wheel turns once `picked` changes; `zoomed` then has those roles' games. */
  let {
    games,
    none,
    zoomed = games,
    picked = [],
    onpick,
  }: { games: Game[]; none: string; zoomed?: Game[]; picked?: Role[]; onpick?: (roles: Role[]) => void } = $props()

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
  const point = (r: number, turn: number) => `${r * Math.sin(2 * Math.PI * turn)} ${-r * Math.cos(2 * Math.PI * turn)}`
  /** A ring segment between two radii, clockwise from the top. */
  function segment(inner: number, outer: number, from: number, to: number): string {
    to = Math.min(to, from + 0.9999) // a full circle has no direction to draw in
    const large = to - from > 0.5 ? 1 : 0
    return `M${point(outer, from)}A${outer} ${outer} 0 ${large} 1 ${point(outer, to)}L${point(inner, to)}A${inner} ${inner} 0 ${large} 0 ${point(inner, from)}Z`
  }
  const ICON = 15 // in the wheel's units; a slice shorter than this along its arc gets no hero icon
  const ICON_AT = 78
  const fits = (share: number) => share * 2 * Math.PI * ICON_AT >= ICON + 2
  const GLYPH_AT = 46 // the middle ring's centre line
  /** A role icon's size in a part `share` long: 16 at most, less where the part's arc at the icon's inner edge is
   *  shorter; under 6 the part gets none. */
  const glyph = (share: number) => Math.min(16, share * 2 * Math.PI * 38 - 2)
  // the role icons in public/roles; the lanes on team pages borrow their position's
  const MARKS = new Map<Role, string>([
    [1, 'carry'], [2, 'mid'], [3, 'offlane'], [4, 'soft-support'], [5, 'hard-support'],
    ['safe', 'carry'], ['mid', 'mid'], ['off', 'offlane'],
  ])
  const SLIVER = 5 // in the wheel's units: a hero slice narrower than this at the outer edge reads as a gap

  // ---- the roles picked fill the whole middle ring, the others shrink to nothing; none picked shows every role at its share
  let own = $state<Role[]>([]) // what a click picked, when no one outside keeps it (team pages)
  const chosen = $derived(onpick ? picked : own)
  const pick = (roles: Role[]) => (onpick ? onpick(roles) : (own = roles))
  const KEYS = [...ROLES.keys()]
  /** Each role's share of the middle ring with `roles` picked, in the order of ROLES; picked roles without games show all. */
  function sizes(roles: Role[]): number[] {
    const counts = KEYS.map((id) => (roles.length && !roles.includes(id) ? 0 : games.filter((g) => g.role === id).length))
    const sum = counts.reduce((a, b) => a + b, 0)
    return roles.length && !sum ? sizes([]) : counts.map((n) => n / (sum || 1))
  }
  // a pick moves every role's share in a straight line from where it is drawn now to its share with the new pick, so
  // the old pick folds while the new one unfolds; `before` is the pick whose heroes the outer ring shows until half way
  let leg = $state({ from: [] as number[], before: [] as Role[], after: [] as Role[] })
  const move = new Tween(1, { easing: cubicInOut })
  const weights = $derived.by(() => {
    const to = sizes(leg.after)
    return leg.from.length ? to.map((w, i) => leg.from[i] + move.current * (w - leg.from[i])) : to
  })
  $effect(() => {
    const next = chosen
    untrack(() => {
      if (next.join() === leg.after.join()) return
      leg = { from: weights, before: move.current > 0.5 ? leg.after : leg.before, after: next }
      move.set(0, { duration: 0 })
      move.set(1, { duration: prefersReducedMotion.current ? 0 : 700 })
    })
  })
  /** Each role with games, its slice of the middle ring as drawn now; `from` and `to` are turns. */
  const wheel = $derived.by(() => {
    let at = 0
    return KEYS.flatMap((id, i) => {
      const mine = games.filter((g) => g.role === id)
      if (!mine.length) return []
      const from = at
      return [{ id, ...ROLES.get(id)!, games: mine.length, wins: mine.filter((g) => g.win).length, from, to: (at += weights[i]) }]
    })
  })
  const alone = $derived(leg.after.length > 0)
  const focusGames = $derived(zoomed.filter((g) => leg.after.includes(g.role)))
  const GROUPS: Record<string, string> = { '1,2,3': 'cores', '4,5': 'supports' }
  /** What fits in the wheel's hole: "Pos 4 (soft support)" → "soft support", "Safe lane" → "safe lane". */
  const short = (title: string) => (title.match(/\((.*)\)/)?.[1] ?? title).toLowerCase()

  // ---- the outer ring: each hero once over all roles, or over the picked ones; it switches half way through a move.
  // Heroes thinner than SLIVER merge into one grey "+N" slice at the end, `others`, when there are at least two.
  const ringRoles = $derived(move.current > 0.5 ? leg.after : leg.before)
  const ringGames = $derived(ringRoles.length ? zoomed.filter((g) => ringRoles.includes(g.role)) : games)
  const ring = $derived.by(() => {
    const all = tally(ringGames)
    const small = all.filter((t) => (t.games / ringGames.length) * 2 * Math.PI * 97 < SLIVER)
    const others = small.length > 1 ? small : []
    let at = 0
    const slice = (hero_id: number, games: number, wins: number, others: Tally[]) =>
      ({ hero_id, games, wins, others, from: at, to: (at += games / ringGames.length) })
    return [
      ...all.filter((t) => !others.includes(t)).map((t) => slice(t.hero_id, t.games, t.wins, [])),
      ...(others.length ? [slice(0, others.reduce((n, t) => n + t.games, 0), others.reduce((n, t) => n + t.wins, 0), others)] : []),
    ]
  })
</script>

<div class="wheel">
  <svg viewBox="-100 -100 200 200" role="group" aria-label="Roles and heroes of the last {games.length} matches; click a part of the middle ring to see it alone; each part and hero names its numbers on hover">
    {#each wheel as role (role.id)}
      <path
        class="role"
        class:pick={!alone}
        d={segment(36, 56, role.from, role.to)}
        style:fill="var(--{role.color})"
        role="button"
        tabindex={alone ? -1 : 0}
        onclick={() => !alone && pick([role.id])}
        onkeydown={(e) => !alone && (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), pick([role.id]))}
      >
        <title>{role.title}: {record(role.wins, role.games)}</title>
      </path>
      {#if glyph(role.to - role.from) >= 6}
        {@const turn = (role.from + role.to) / 2}
        {@const size = glyph(role.to - role.from)}
        {@const x = GLYPH_AT * Math.sin(2 * Math.PI * turn)}
        {@const y = -GLYPH_AT * Math.cos(2 * Math.PI * turn)}
        {#if MARKS.has(role.id)}
          <image class="glyph" href="/roles/{MARKS.get(role.id)}.png" x={x - size / 2} y={y - size / 2} width={size} height={size} />
        {:else}
          <g class="glyph" transform="translate({x} {y}) scale({size / 12})">
            {#if role.id === 'jungle'}<path class="lane" d="M-3 1l2-4 2 4zM0 4l2-4 2 4z" />{:else}<text class="unknown" y="3.5">?</text>{/if}
          </g>
        {/if}
      {/if}
    {/each}
    <!-- fades out and back in around a move's half way, where the ring switches to the picked roles' heroes -->
    <g style:opacity={Math.abs(2 * move.current - 1)}>
      {#each ring as s (s.hero_id)}
        {@const middle = (s.from + s.to) / 2}
        {@const x = ICON_AT * Math.sin(2 * Math.PI * middle)}
        {@const y = -ICON_AT * Math.cos(2 * Math.PI * middle)}
        <g class="slice">
          {#if s.others.length}
            <title>{s.others.length} heroes with few matches: {record(s.wins, s.games)}{s.others.map((t) => `
${heroName(t.hero_id)}: ${record(t.wins, t.games)}`).join('')}</title>
            <path d={segment(59, 97, s.from, s.to)} />
            {#if fits(s.to - s.from)}<text class="others" {x} y={y + 3}>+{s.others.length}</text>{/if}
          {:else}
            <title>{heroName(s.hero_id)}: {record(s.wins, s.games)}</title>
            <path d={segment(59, 97, s.from, s.to)} class:winning={s.wins * 2 >= s.games} class:losing={s.wins * 2 < s.games} />
            {#if fits(s.to - s.from)}<image href={heroIcon(s.hero_id)} x={x - ICON / 2} y={y - ICON / 2} width={ICON} height={ICON} />{/if}
          {/if}
        </g>
      {/each}
    </g>
    <text class="count" y="2">{alone ? focusGames.length : games.length}</text>
    <text class="unit" y="15">{alone ? (GROUPS[leg.after.join()] ?? short(ROLES.get(leg.after[0])!.title)) : 'matches'}</text>
  </svg>
  {#if alone}<button class="action" onclick={() => pick([])}>Show all roles</button>{/if}
</div>

<style>
  .wheel {
    width: 100%;
    max-width: 380px;
    margin: 0 auto;
    display: grid;
    justify-items: center;
    gap: 8px;
  }
  .wheel svg {
    width: 100%;
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
  /* a hero's slice is tinted by its win rate: green from half up, red below; the others slice stays grey */
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
  .slice image,
  .others {
    pointer-events: none;
  }
  .others {
    font-size: 9px;
    font-weight: 700;
    fill: var(--muted);
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
  /* clicks go through to the slice under it */
  .glyph {
    pointer-events: none;
    fill: none;
    stroke: #fff;
  }
  .glyph .lane {
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .glyph .unknown {
    font-size: 9px;
    font-weight: 800;
    fill: #fff;
    stroke: none;
  }
</style>
