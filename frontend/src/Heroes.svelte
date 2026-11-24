<script lang="ts">
  import { untrack } from 'svelte'
  import { clock, type MatchRow } from './lib/api'
  import { heroName, heroPortrait, itemIcon, itemName } from './lib/constants.svelte'
  import Count from './lib/Count.svelte'
  import { MARKS } from './lib/RoleWheel.svelte'
  import WinRate from './lib/WinRate.svelte'
  import Matches from './Matches.svelte'

  /** `matches` are the profile's matches for the same query, newest first: the table sums them per hero, and a hero
   *  unfolds into its own, as on the Matches tab. `open` is a hero unfolded from the start (one clicked on the Overview), 0 for none. */
  let { matches, open = 0 }: { matches: MatchRow[]; open?: number } = $props()

  type Row = {
    hero_id: number
    games: MatchRow[] // newest first, as `matches`
    wins: number
    kills: number // the averages over its games, as all the numbers below
    deaths: number
    assists: number
    gpm: number
    xpm: number
    lh: number
    dn: number
    duration: number
    last: number // start_time of its newest game
    positions: [number, number][] // [position, games], most games first
  }
  const mean = (games: MatchRow[], value: (m: MatchRow) => number) => games.reduce((sum, m) => sum + value(m), 0) / games.length
  const rows = $derived.by(() => {
    const by = new Map<number, MatchRow[]>()
    for (const m of matches) by.set(m.hero_id, [...(by.get(m.hero_id) ?? []), m])
    return [...by].map(([hero_id, games]): Row => {
      const positions = new Map<number, number>()
      for (const m of games) if (MARKS.has(m.position)) positions.set(m.position, (positions.get(m.position) ?? 0) + 1)
      return {
        hero_id,
        games,
        wins: games.filter((m) => m.win).length,
        kills: mean(games, (m) => m.kills),
        deaths: mean(games, (m) => m.deaths),
        assists: mean(games, (m) => m.assists),
        gpm: mean(games, (m) => m.gold_per_min),
        xpm: mean(games, (m) => m.xp_per_min),
        lh: mean(games, (m) => m.last_hits),
        dn: mean(games, (m) => m.denies),
        duration: mean(games, (m) => m.duration),
        last: games[0].start_time,
        positions: [...positions].sort((a, b) => b[1] - a[1]),
      }
    })
  })

  // ---- sorting as on the Matches tab; a tie (3 of 3 and 1 of 1 won) goes to the hero with more games
  const SORTS = {
    games: (r: Row) => r.games.length,
    rate: (r: Row) => r.wins / r.games.length,
    kda: (r: Row) => (r.kills + r.assists) / Math.max(1, r.deaths),
    gpm: (r: Row) => r.gpm,
    xpm: (r: Row) => r.xpm,
    lh: (r: Row) => r.lh,
    duration: (r: Row) => r.duration,
    last: (r: Row) => r.last,
  }
  type Key = keyof typeof SORTS
  let sort = $state<{ key: Key; down: boolean }>({ key: 'games', down: true })
  const sortBy = (key: Key) => (sort = { key, down: sort.key === key ? !sort.down : true })

  const MIN_GAMES = [1, 3, 5]
  let minGames = $state(1)
  const shown = $derived.by(() => {
    const { key, down } = sort
    return rows
      .filter((r) => r.games.length >= minGames)
      .sort((a, b) => (down ? SORTS[key](b) - SORTS[key](a) : SORTS[key](a) - SORTS[key](b)) || b.games.length - a.games.length)
  })
  const most = $derived(Math.max(0, ...rows.map((r) => r.games.length)))

  /** The items most often in the hero's final six slots: [item, games it was in], at most COMMON of them */
  const COMMON = 8
  function common(games: MatchRow[]): [number, number][] {
    const count = new Map<number, number>()
    for (const m of games) for (const id of new Set(m.items.slice(0, 6))) if (id) count.set(id, (count.get(id) ?? 0) + 1)
    return [...count].sort((a, b) => b[1] - a[1]).slice(0, COMMON)
  }

  const DAY = 86400000
  function ago(seconds: number) {
    const days = Math.round((new Date(new Date().toDateString()).getTime() - new Date(new Date(seconds * 1000).toDateString()).getTime()) / DAY)
    if (days === 0) return 'Today'
    if (days === 1) return 'Yesterday'
    if (days < 30) return `${days} days ago`
    return new Date(seconds * 1000).toLocaleDateString('en-GB', { dateStyle: 'medium' })
  }
  const role = (position: number) => `Pos ${position} (${MARKS.get(position)!.replace('-', ' ')})`

  let unfolded = $state<number[]>(untrack(() => (open ? [open] : [])))
  const unfold = (id: number) => (unfolded = unfolded.includes(id) ? unfolded.filter((o) => o !== id) : [...unfolded, id])
  // a click anywhere on the row unfolds it, except on its buttons
  const unfoldRow = (e: MouseEvent, id: number) => !(e.target as Element).closest('a, button') && unfold(id)
  const COLUMNS = 11
</script>

{#snippet header(label: string, key: Key, num = true)}
  <th class:num aria-sort={sort.key === key ? (sort.down ? 'descending' : 'ascending') : undefined}>
    <button onclick={() => sortBy(key)}>
      {label}<span class="arrow" aria-hidden="true">{sort.key === key ? (sort.down ? '▾' : '▴') : ''}</span>
    </button>
  </th>
{/snippet}

{#if rows.length === 0}
  <p class="muted">No matches for these filters.</p>
{:else}
  <div class="filters">
    <span>At least</span>
    <span class="choice" role="group" aria-label="Fewest games of a hero shown">
      {#each MIN_GAMES as n}
        <button aria-pressed={minGames === n} onclick={() => (minGames = n)}>{n}+</button>
      {/each}
    </span>
    <span>games</span>
    <span class="muted">{shown.length} of {rows.length} heroes</span>
  </div>
  <div class="card tall">
    <table>
      <thead>
        <tr>
          <th></th>
          <th>Hero</th>
          <th>Roles</th>
          {@render header('Games', 'games', false)}
          {@render header('Win rate', 'rate', false)}
          {@render header('K / D / A', 'kda')}
          {@render header('GPM', 'gpm')}
          {@render header('XPM', 'xpm')}
          {@render header('LH / DN', 'lh')}
          {@render header('Duration', 'duration')}
          {@render header('Last played', 'last')}
        </tr>
      </thead>
      <tbody>
        {#each shown as r (r.hero_id)}
          {@const open = unfolded.includes(r.hero_id)}
          <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions (the arrow button is the keyboard way) -->
          <tr class="folds" onclick={(e) => unfoldRow(e, r.hero_id)}>
            <td>
              <button class="unfold" aria-expanded={open} aria-label="Matches on {heroName(r.hero_id)}" onclick={() => unfold(r.hero_id)}>{open ? '▾' : '▸'}</button>
            </td>
            <td class="hero"><img src={heroPortrait(r.hero_id)} alt={heroName(r.hero_id)} title={heroName(r.hero_id)} width="44" height="25" loading="lazy" /></td>
            <td class="roles">
              {#each r.positions as [position, games]}
                {@const title = `${role(position)}: ${games} ${games === 1 ? 'game' : 'games'}`}
                <img src="/roles/{MARKS.get(position)}.png" alt={title} {title} width="18" height="18" />
              {/each}
            </td>
            <td><Count games={r.games.length} max={most} /></td>
            <td><WinRate wins={r.wins} games={r.games.length} /></td>
            <td class="num">{r.kills.toFixed(1)} / {r.deaths.toFixed(1)} / {r.assists.toFixed(1)}</td>
            <td class="num">{Math.round(r.gpm)}</td>
            <td class="num">{Math.round(r.xpm)}</td>
            <td class="num">{Math.round(r.lh)} / {Math.round(r.dn)}</td>
            <td class="num">{clock(Math.round(r.duration))}</td>
            <td class="num" title={new Date(r.last * 1000).toLocaleString('en-GB')}>{ago(r.last)}</td>
          </tr>
          {#if open}
            <tr class="more">
              <td colspan={COLUMNS}>
                <p class="common">
                  <span class="muted">Most common items</span>
                  {#each common(r.games) as [id, games]}
                    {@const title = `${itemName(id)}: in ${games} of ${r.games.length} games`}
                    <span class="item">
                      {#if itemIcon(id)}<img src={itemIcon(id)} alt={itemName(id)} {title} width="33" height="24" loading="lazy" />{:else}{itemName(id)}{/if}
                      <small>{games}/{r.games.length}</small>
                    </span>
                  {/each}
                </p>
                <Matches given={r.games} />
              </td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .hero img {
    display: block;
    object-fit: cover;
    border-radius: 3px;
  }
  .roles {
    white-space: nowrap;
  }
  .roles img {
    margin-right: 4px;
    vertical-align: middle;
    opacity: 0.85;
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
  .common {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 14px;
    max-width: none; /* a row of icons, not reading text: the page's 78ch would wrap it early */
    margin: 0 0 12px;
  }
  .item {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .item img {
    border-radius: 3px;
  }
  .item small {
    color: var(--text-2);
    font-size: 12px;
  }
</style>
