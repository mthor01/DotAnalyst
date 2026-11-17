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
  let picked = $state<boolean>() // the side chosen with the buttons; until then the side of their newest game
  const radiant = $derived(picked ?? all[0]?.radiant ?? true)
  const games = $derived(all.filter((g) => g.radiant === radiant).slice(0, GAMES))
  let spots = $state.raw<Record<number, Spot[]>>({}) // match id -> where its heroes were, second by second
  let error = $state('')
  let at = $state(UNTIL)
  let hidden = $state<Record<number, boolean>>({}) // match id -> switched off beside the map
  const all_on = $derived(games.every((g) => !hidden[g.match_id]))

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

<div class="openings">
<div class="board">
<MiniMap label="Where the team's heroes walked from {clock(FROM)} to {clock(at)} in their last {games.length} games as {radiant ? 'Radiant' : 'Dire'}">
  {#snippet controls()}
    <!-- one side at a time: its six games take the six colours -->
    {#each [true, false] as side}
      <button class="toggle" style:--tint="var(--{side ? 'radiant' : 'dire'})" aria-pressed={radiant === side}
        onclick={() => (picked = side)}><i></i>As {side ? 'Radiant' : 'Dire'}</button>
    {/each}
  {/snippet}
  {#snippet children(size)}
    {#each ways.filter((w) => !hidden[games[w.n].match_id] && w.way.length) as w (w.key)}
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
</div>
<!-- beside the map: which games it draws, each a button in its game's colour -->
<ol aria-label="Games drawn on the map">
  {#if games.length}
    <li><button class="game" aria-pressed={all_on} onclick={() => (hidden = {})}>All games</button></li>
  {/if}
  {#each games as g, n (g.match_id)}
    <li class:none={!g.replay}>
      <button class="game" style:--game="var(--series-{n + 1})" aria-pressed={!hidden[g.match_id]}
        onclick={() => (hidden = { ...hidden, [g.match_id]: !hidden[g.match_id] })}>
        <i></i>{date(g.start_time)}
      </button>
      against {g.opponent || 'a side without a team'}, {g.win ? 'won' : 'lost'}{g.replay ? '' : ': no replay'}
      <a href="#match/{g.match_id}" aria-label="Open the game of {date(g.start_time)}">open</a>
    </li>
  {:else}
    <li>No games of theirs as {radiant ? 'Radiant' : 'Dire'} in this season and time frame.</li>
  {/each}
</ol>
</div>
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
  .openings {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 12px 24px;
  }
  .board {
    flex: 1 1 320px;
    max-width: 520px;
  }
  ol {
    display: grid;
    gap: 6px;
    margin: 0 0 12px;
    padding: 0;
    list-style: none;
    color: var(--text-2);
  }
  /* on: the game's colour fills the dot and edges the button; off: a hollow dot on a muted button */
  .game {
    font: inherit;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-width: 92px;
    margin-right: 6px;
    padding: 3px 10px;
    border: 1px solid var(--axis);
    border-radius: 4px;
    background: none;
    color: var(--muted);
    cursor: pointer;
  }
  .game i {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    border: 2px solid var(--game);
  }
  .game[aria-pressed='true'] {
    border-color: var(--game, var(--text-2));
    background: var(--raised);
    color: var(--text);
  }
  .game[aria-pressed='true'] i {
    background: var(--game);
  }
  li.none {
    color: var(--muted);
  }
</style>
