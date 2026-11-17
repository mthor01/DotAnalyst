<script lang="ts">
  import { get, percent, type Account, type MatchRow, type WardSpot } from './lib/api'
  import { heroIcon, heroName } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'
  import RoleWheel, { tally, type Role } from './lib/RoleWheel.svelte'
  import WardHeat from './lib/WardHeat.svelte'

  let { query, account }: { query: string; account: Account | undefined } = $props()
  let rows = $state<MatchRow[]>([])
  let wards = $state.raw<(WardSpot & { match_id: number })[]>([]) // of every match of these filters
  let error = $state('')
  let size = $state(25)
  let role = $state(0) // index into ROLES

  $effect(() => {
    let current = true
    Promise.all([get<MatchRow[]>('matches', query), get<typeof wards>('wards', query)]).then(
      ([found, placed]) => current && ((rows = found), (wards = placed), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const SIZES = [25, 100, 500]
  /** The role picker: a name and the positions it takes in (see Position 1–5 in IMPLEMENTATION.md) */
  const ROLES: [string, number[]][] = [
    ['All roles', [1, 2, 3, 4, 5]],
    ['Pos 1 (carry)', [1]],
    ['Pos 2 (mid)', [2]],
    ['Pos 3 (offlane)', [3]],
    ['Pos 4 (soft support)', [4]],
    ['Pos 5 (hard support)', [5]],
    ['Cores (pos 1–3)', [1, 2, 3]],
    ['Supports (pos 4–5)', [4, 5]],
  ]
  const TOP_HEROES = 10
  const EVEN = 500 // a lane within this much net worth at 10:00 counts as even
  const played = $derived(rows.filter((r) => ROLES[role][1].includes(r.position)))
  const recent = $derived(played.slice(0, size)) // the API returns newest first
  const as = $derived(role ? ` as ${ROLES[role][0].toLowerCase()}` : '')
  const wins = $derived(recent.filter((r) => r.win).length)
  const share = (part: number) => `${percent(part, recent.length)}%`
  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString(undefined, { dateStyle: 'medium' })

  // ---- roles: the lane seen from the player's side. Radiant's safe lane is bottom, Dire's is top.
  function roleOf(r: MatchRow): Role {
    if (r.lane === 'top' || r.lane === 'bot') return (r.lane === 'bot') === r.radiant ? 'safe' : 'off'
    return r.lane ?? 'none'
  }
  const heroes = $derived(tally(recent))
  const roles = $derived(recent.map((r) => ({ ...r, role: roleOf(r) })))

  // ---- the strip: one column per match, oldest on the left
  const strip = $derived([...recent].reverse())
  const reach = $derived(Math.max(1000, ...recent.map((r) => Math.abs(r.lane_nw_diff ?? 0))))
  const signed = (n: number) => `${n > 0 ? '+' : ''}${Math.round(n).toLocaleString()}`
  const note = (r: MatchRow) =>
    `${heroName(r.hero_id)}, ${date(r.start_time)}: ${r.win ? 'won' : 'lost'}` +
    (r.lane_nw_diff === null ? '' : `, lane ${signed(r.lane_nw_diff)} net worth at 10:00`)

  // ---- the ward heatmap: the wards of the matches shown
  const warded = $derived.by(() => {
    const shown = new Set(recent.map((r) => r.match_id))
    return wards.filter((w) => shown.has(w.match_id))
  })
  const parsed = $derived(recent.filter((r) => r.replay_state === 'parsed').length)

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
    <h2>
      {#if account?.avatar}<img class="avatar" src={account.avatar} alt="" width="40" height="40" />{/if}
      {account?.label ?? account?.account_id}
    </h2>
    <p class="muted">The last {recent.length} of {played.length} matches{as} for these filters</p>
    <label class="role">
      Role
      <select bind:value={role}>
        {#each ROLES as [name], i}<option value={i}>{name}</option>{/each}
      </select>
    </label>
    <div class="choice" role="group" aria-label="How many matches">
      {#each SIZES as n}
        <button aria-pressed={size === n} onclick={() => (size = n)}>{n} matches</button>
      {/each}
    </div>
  </header>

  {#if recent.length === 0}
    <p class="muted">No matches{as} for these filters. Pick another role above.</p>
  {:else}
  <div class="overview">
    <section class="card roles">
      <RoleWheel games={roles} none="No replay" />
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
    <div class="strip" class:dense={size > 25} class:packed={size > 100}>
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

  <section class="card vision">
    <div>
      <WardHeat wards={warded} label="Heatmap of the wards {account?.label ?? 'the player'} placed in these matches" />
    </div>
    <div class="muted">
      <h3>Wards placed</h3>
      <p>
        Where the wards went in the {parsed} of these {recent.length} matches that have a parsed replay. Every ward
        warms the map around its spot; red is a spot warded now and then, yellow to white the spots warded most.
      </p>
      <p>
        Radiant and Dire ward different places, so the buttons above the map show one side's games alone, or one kind
        of ward. Scroll over the map to zoom, drag to move it, hover a spot for its count.
      </p>
    </div>
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
  .role {
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
