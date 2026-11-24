<script lang="ts">
  import { EVEN, GAME_MODES, LOBBY_TYPES, clock, get, type MatchRow } from './lib/api'
  import { constants, itemIcon } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'
  import ReplaySign from './lib/ReplaySign.svelte'
  import { MARKS } from './lib/RoleWheel.svelte'
  import Match from './Match.svelte'

  /** `given` shows those matches instead of fetching the query's (a hero's on the Heroes tab) */
  let { query = '', given }: { query?: string; given?: MatchRow[] } = $props()
  let fetched = $state<MatchRow[]>([])
  const rows = $derived(given ?? fetched)
  let error = $state('')

  $effect(() => {
    if (given) return
    let current = true // a slower, older request must not overwrite a newer one
    get<MatchRow[]>('matches', query).then(
      (found) => current && ((fetched = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  // ---- sorting: a header click sorts by its column, a second click flips it; matches without the value go last
  const SORTS = {
    date: (r: MatchRow) => r.start_time,
    lane: (r: MatchRow) => r.lane_nw_diff,
    kda: (r: MatchRow) => (r.kills + r.assists) / Math.max(1, r.deaths),
    gpm: (r: MatchRow) => r.gold_per_min,
    xpm: (r: MatchRow) => r.xp_per_min,
    lh: (r: MatchRow) => r.last_hits,
    duration: (r: MatchRow) => r.duration,
  }
  type Key = keyof typeof SORTS
  let sort = $state<{ key: Key; down: boolean }>({ key: 'date', down: true })
  const sortBy = (key: Key) => (sort = { key, down: sort.key === key ? !sort.down : true })
  const sorted = $derived.by(() => {
    const { key, down } = sort
    return rows.toSorted((a, b) => {
      const x = SORTS[key](a), y = SORTS[key](b)
      return x === null ? (y === null ? 0 : 1) : y === null ? -1 : down ? y - x : x - y
    })
  })

  // ---- the first PAGE rows, more on asking; a new set of matches starts over
  const PAGE = 50
  let limit = $derived.by(() => (rows, PAGE))
  const shown = $derived(sorted.slice(0, limit))

  // ---- in date order the rows fall under a header per day, with the day's wins and losses (of all its matches)
  const dayOf = (seconds: number) => new Date(seconds * 1000).toDateString()
  const days = $derived.by(() => {
    const found = new Map<string, { won: number; lost: number }>()
    for (const r of rows) {
      const d = found.get(dayOf(r.start_time)) ?? { won: 0, lost: 0 }
      found.set(dayOf(r.start_time), r.win ? { ...d, won: d.won + 1 } : { ...d, lost: d.lost + 1 })
    }
    return found
  })
  const dayTitle = (seconds: number) => {
    const day = new Date(seconds * 1000), today = new Date()
    const ago = Math.round((new Date(today.toDateString()).getTime() - new Date(day.toDateString()).getTime()) / 86400000)
    if (ago === 0) return 'Today'
    if (ago === 1) return 'Yesterday'
    const year = day.getFullYear() === today.getFullYear() ? undefined : 'numeric'
    return day.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year })
  }
  const time = (seconds: number) => new Date(seconds * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString('en-GB', { dateStyle: 'medium' })

  const laneResult = (diff: number) => (diff > EVEN ? 'won' : diff < -EVEN ? 'lost' : 'even')
  const signed = (n: number) => (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(Math.round(n)).toLocaleString('en-GB')
  const itemName = (id: number) => constants.items[id]?.replaceAll('_', ' ') ?? `Item ${id}`

  let unfolded = $state<number[]>([])
  const unfold = (id: number) => (unfolded = unfolded.includes(id) ? unfolded.filter((o) => o !== id) : [...unfolded, id])
  // a click anywhere on the row unfolds it, except on its links and buttons, which do their own thing
  const unfoldRow = (e: MouseEvent, id: number) => !(e.target as Element).closest('a, button') && unfold(id)
  const COLUMNS = 13
</script>

{#snippet header(label: string, key: Key, num = true)}
  <th class:num aria-sort={sort.key === key ? (sort.down ? 'descending' : 'ascending') : undefined}>
    <button class="sort" onclick={() => sortBy(key)}>
      {label}<span class="arrow" aria-hidden="true">{sort.key === key ? (sort.down ? '▾' : '▴') : ''}</span>
    </button>
  </th>
{/snippet}

{#if error}
  <p class="error" role="alert">{error}</p>
{:else}
  <div class="card tall">
    <table>
      <thead>
        <tr>
          <th></th>
          {@render header(sort.key === 'date' ? 'Time' : 'Date', 'date', false)}
          <th>Hero</th>
          <th>Party</th>
          {@render header('Lane', 'lane', false)}
          {@render header('K / D / A', 'kda')}
          {@render header('GPM', 'gpm')}
          {@render header('XPM', 'xpm')}
          {@render header('LH / DN', 'lh')}
          {@render header('Duration', 'duration')}
          <th>Items</th>
          <th>Parse</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each shown as r, i (r.match_id)}
          {@const open = unfolded.includes(r.match_id)}
          {@const result = r.win ? 'won' : 'lost'}
          {#if sort.key === 'date' && (i === 0 || dayOf(r.start_time) !== dayOf(shown[i - 1].start_time))}
            {@const tally = days.get(dayOf(r.start_time))!}
            <tr class="day">
              <th colspan={COLUMNS} scope="rowgroup">
                {dayTitle(r.start_time)}
                <span class="tally"><span class="good">{tally.won} W</span> <span class="bad">{tally.lost} L</span></span>
              </th>
            </tr>
          {/if}
          <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions (the arrow button is the keyboard way) -->
          <tr class="folds" onclick={(e) => unfoldRow(e, r.match_id)}>
            <td class="edge {result}" title={r.win ? 'Won' : 'Lost'}>
              <button
                class="unfold"
                aria-expanded={open}
                aria-label="Details of the {result} match on {date(r.start_time)}"
                onclick={() => unfold(r.match_id)}>{open ? '▾' : '▸'}</button
              >
            </td>
            <td class="when">
              {sort.key === 'date' ? time(r.start_time) : date(r.start_time)}
              <small class="muted">{LOBBY_TYPES[r.lobby_type] ?? `Lobby ${r.lobby_type}`} {GAME_MODES[r.game_mode] ?? `Mode ${r.game_mode}`}</small>
            </td>
            <td class="hero">
              <Hero id={r.hero_id} />
              {#if MARKS.has(r.position)}
                {@const title = `Pos ${r.position} (${MARKS.get(r.position)!.replace('-', ' ')})`}
                <img class="role" src="/roles/{MARKS.get(r.position)}.png" alt={title} {title} width="18" height="18" />
              {/if}
            </td>
            <td>
              {#if r.party_size > 1}
                <span
                  class="party"
                  class:tracked={r.with_tracked}
                  title="Queued in a party of {r.party_size}{r.with_tracked ? ', with a tracked player on the team' : ''}"
                >
                  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"
                    ><circle cx="5.5" cy="5" r="2.6" /><path d="M0.5 14c0-3 2.2-5 5-5s5 2 5 5z" /><circle cx="11.5" cy="4.5" r="2.2" opacity=".6" /><path
                      d="M11.5 8.2c2.4 0 4 1.8 4 4.8h-4z"
                      opacity=".6"
                    /></svg
                  >{r.party_size}
                </span>
              {:else}
                <span class="muted" title="Queued alone">–</span>
              {/if}
            </td>
            <td>
              {#if r.lane_nw_diff === null}
                <span class="muted" title={r.lane === 'jungle' ? 'Jungle: no lane to compare' : 'No lane result: needs a parsed replay of a lane'}>–</span>
              {:else}
                {@const lane = laneResult(r.lane_nw_diff)}
                <span class={lane === 'won' ? 'good' : lane === 'lost' ? 'bad' : ''} title="{signed(r.lane_nw_diff)} net worth at 10:00 against the enemy lane (even within {EVEN})">
                  {lane === 'won' ? 'Won' : lane === 'lost' ? 'Lost' : 'Even'}
                </span>
              {/if}
            </td>
            <td class="num">{r.kills} / {r.deaths} / {r.assists}</td>
            <td class="num">{r.gold_per_min}</td>
            <td class="num">{r.xp_per_min}</td>
            <td class="num">{r.last_hits} / {r.denies}</td>
            <td class="num">{clock(r.duration)}</td>
            <td class="items">
              {#each r.items.slice(0, 6) as id}
                {#if id && itemIcon(id)}
                  <img src={itemIcon(id)} alt={itemName(id)} title={itemName(id)} width="26" height="19" loading="lazy" />
                {:else}
                  <span class="slot"></span>
                {/if}
              {/each}
              {#if r.items[6] && itemIcon(r.items[6])}
                <img class="neutral" src={itemIcon(r.items[6])} alt={itemName(r.items[6])} title="{itemName(r.items[6])} (neutral)" width="19" height="19" loading="lazy" />
              {/if}
            </td>
            <td class="muted"><ReplaySign match_id={r.match_id} state={r.replay_state} start_time={r.start_time} /></td>
            <td><a class="open" href="#match/{r.match_id}" title="Open the match" aria-label="Open the match on {date(r.start_time)}">↗</a></td>
          </tr>
          {#if open}<tr class="more"><td colspan={COLUMNS}><Match id={String(r.match_id)} brief draft={false} /></td></tr>{/if}
        {/each}
      </tbody>
    </table>
  </div>
  {#if sorted.length > limit}
    <p class="more-rows">
      <button onclick={() => (limit += PAGE)}>Show {Math.min(PAGE, sorted.length - limit)} more</button>
      <span class="muted">{sorted.length - limit} not shown yet</span>
    </p>
  {/if}
{/if}

<style>
  /* six slots in one line, empty ones kept so the columns line up, then the neutral item round */
  .items {
    white-space: nowrap;
    line-height: 0;
  }
  .items img,
  .slot {
    display: inline-block;
    width: 26px;
    height: 19px;
    margin-right: 2px;
    vertical-align: middle;
    border-radius: 2px;
  }
  .slot {
    background: var(--page);
  }
  .items .neutral {
    width: 19px;
    margin-left: 4px;
    border-radius: 50%;
    object-fit: cover;
  }
  .when {
    white-space: nowrap;
  }
  .when small {
    display: block;
    font-size: 11px;
  }
  .hero {
    white-space: nowrap;
  }
  .role {
    margin-left: 6px;
    vertical-align: middle;
    opacity: 0.85;
  }
  .party {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--text-2);
    fill: currentColor;
  }
  .party.tracked {
    color: var(--series-1);
  }
  .good {
    color: var(--good);
  }
  .bad {
    color: var(--critical);
  }
  /* the result is the row's left edge */
  .edge.won {
    box-shadow: inset 3px 0 0 var(--good);
  }
  .edge.lost {
    box-shadow: inset 3px 0 0 var(--critical);
  }
  .day th {
    padding: 14px 12px 6px;
    background: var(--page);
    color: var(--text);
    font-size: 13px;
    font-weight: 600;
    text-align: left;
  }
  .day .tally {
    margin-left: 10px;
    font-size: 12px;
    font-weight: 500;
  }
  /* thirteen columns: narrower gaps than the site's tables so the row fits the card */
  th,
  td {
    padding-inline: 8px;
  }
  .sort:hover {
    color: var(--text);
  }
  .arrow {
    display: inline-block;
    width: 0.8em;
    margin-left: 2px;
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
  .more-rows {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 12px 0 0;
  }
</style>
