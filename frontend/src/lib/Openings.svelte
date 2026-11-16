<script lang="ts">
  import { clock, get, post, type TeamDetail } from './api'
  import { heroIcon, heroName } from './constants.svelte'
  import MiniMap, { mapX, mapY } from './MiniMap.svelte'

  type Game = TeamDetail['games'][number]
  type Spot = { time: number; player_slot: number; x: number; y: number }
  /** The team's games, newest first, and what to do once a replay asked for here has arrived. */
  let { games: all, onfetched }: { games: Game[]; onfetched: () => void } = $props()

  const FROM = -90 // the heroes appear 89 seconds before the horn
  const UNTIL = 30
  const LEAP = 8 // cells in one second: a teleport, not a walk (as in Playback)
  const GAMES = 6 // per side, one colour each
  let picked = $state<boolean>() // the side chosen in the dropdown; until then the side of their newest game
  const radiant = $derived(picked ?? all[0]?.radiant ?? true)
  const games = $derived(all.filter((g) => g.radiant === radiant).slice(0, GAMES))
  let spots = $state.raw<Record<number, Spot[]>>({}) // match id -> where its heroes were, second by second
  let error = $state('')
  let at = $state(UNTIL)

  $effect(() => {
    let current = true
    for (const g of games.filter((g) => g.replay)) {
      get<Spot[]>(`matches/${g.match_id}/positions`, `start=${FROM}&end=${UNTIL}`).then(
        (found) => current && (spots = { ...spots, [g.match_id]: found }),
        (e) => current && (error = e.message),
      )
    }
    return () => (current = false)
  })

  /** One hero's way in one game. The team's picks are in slot order, so pick i of a Dire team is slot 128 + i. */
  const ways = $derived(
    games.flatMap((g, n) =>
      g.picks.map((hero_id, i) => {
        const slot = (g.radiant ? 0 : 128) + i
        const way = (spots[g.match_id] ?? []).filter((s) => s.player_slot === slot).sort((a, b) => a.time - b.time)
        return { key: `${g.match_id} ${slot}`, n, hero_id, way }
      }),
    ),
  )
  /** The way walked up to `until` as an SVG path; a teleport lifts the pen. */
  function line(way: Spot[], until: number) {
    let d = ''
    way.forEach((s, i) => {
      if (s.time > until) return
      const before = way[i - 1]
      const walked = before && Math.hypot(s.x - before.x, s.y - before.y) <= LEAP
      d += `${walked ? 'L' : 'M'}${mapX(s.x).toFixed(1)} ${mapY(s.y).toFixed(1)}`
    })
    return d
  }
  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
  const layers = $derived([
    { '': 'All games', ...Object.fromEntries(games.map((g, n) => [`game${n}`, `${n + 1}: ${date(g.start_time)}`])) },
  ])

  // ---- the replays that are not here yet: asked for one after the other, each about 15 seconds
  const missing = $derived(games.filter((g) => !g.replay))
  let asking = $state('')
  let asked = $state('')
  async function request() {
    const left: string[] = []
    try {
      for (const [i, g] of missing.entries()) {
        asking = `Fetching replay ${i + 1} of ${missing.length}…`
        const { replay_state } = await post<{ replay_state: string }>(`matches/${g.match_id}/replay`)
        if (replay_state !== 'parsed') left.push(`${date(g.start_time)}: ${replay_state === 'unavailable' ? 'Valve no longer has it' : 'not there yet'}`)
      }
      asked = left.join('; ')
    } catch (e) {
      asked = (e as Error).message
    }
    asking = ''
    onfetched()
  }
</script>

<MiniMap label="Where the team's heroes walked from {clock(FROM)} to {clock(at)} in their last {games.length} games as {radiant ? 'Radiant' : 'Dire'}" {layers}>
  {#snippet controls()}
    <select aria-label="Side the games were played on" value={radiant ? 'radiant' : 'dire'}
      onchange={(e) => (picked = e.currentTarget.value === 'radiant')}>
      <option value="radiant">As Radiant</option>
      <option value="dire">As Dire</option>
    </select>
  {/snippet}
  {#snippet children(size, on)}
    {#each ways.filter((w) => on[`game${w.n}`] && w.way.length) as w (w.key)}
      {@const here = w.way.findLast((s) => s.time <= at)}
      <g style:--game="var(--series-{w.n + 1})">
        <path d={line(w.way, at)} stroke-width={size * 0.006} />
        {#if here}
          <g transform="translate({mapX(here.x)} {mapY(here.y)})">
            <title>{heroName(w.hero_id)}, game {w.n + 1}</title>
            <circle r={size * 0.022} stroke-width={size * 0.006} />
            <image href={heroIcon(w.hero_id)} x={-size * 0.018} y={-size * 0.018} width={size * 0.036} height={size * 0.036} />
          </g>
        {/if}
      </g>
    {/each}
  {/snippet}
</MiniMap>
<p class="controls">
  <input type="range" min={FROM} max={UNTIL} step="1" bind:value={at} aria-label="Game second the map shows the heroes at" />
  <span>{clock(at)}</span>
</p>
<ol>
  {#each games as g, n (g.match_id)}
    <li class:none={!g.replay}>
      <i class="swatch" style:background="var(--series-{n + 1})"></i>
      <a href="#match/{g.match_id}">{date(g.start_time)}</a>
      against {g.opponent || 'a side without a team'}, {g.win ? 'won' : 'lost'}{g.replay ? '' : ': no replay'}
    </li>
  {:else}
    <li>No games of theirs as {radiant ? 'Radiant' : 'Dire'} in this season and time frame.</li>
  {/each}
</ol>
{#if error}<p class="error" role="alert">{error}</p>{/if}
{#if missing.length}
  <p>
    <button class="action" onclick={request} disabled={!!asking}>
      {asking || `Request the ${missing.length === 1 ? 'missing replay' : `${missing.length} missing replays`}`}
    </button>
    <span class="muted" role="status">{asking ? '' : asked || `About 15 seconds each.`}</span>
  </p>
{/if}

<style>
  path {
    fill: none;
    stroke: var(--game);
    stroke-linejoin: round;
    opacity: 0.85;
  }
  circle {
    fill: var(--page);
    stroke: var(--game);
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 12px;
    max-width: 520px;
    margin: 10px 0 8px;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  .controls input {
    flex: 1;
    margin: 0;
    padding: 0;
  }
  ol {
    margin: 0 0 12px;
    padding: 0;
    list-style: none;
    color: var(--text-2);
  }
  li.none {
    color: var(--muted);
  }
</style>
