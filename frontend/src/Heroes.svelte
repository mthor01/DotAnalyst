<script lang="ts">
  import { get, sortedBy, type HeroRow, type MatchRow } from './lib/api'
  import { heroName, heroPortrait } from './lib/constants.svelte'
  import Count from './lib/Count.svelte'
  import WinRate from './lib/WinRate.svelte'
  import Matches from './Matches.svelte'

  /** `matches` are the profile's matches for the same query, newest first: a hero unfolds into them, as on the Matches tab */
  let { query, matches }: { query: string; matches: MatchRow[] } = $props()
  let rows = $state<HeroRow[]>([])
  let error = $state('')

  $effect(() => {
    let current = true
    get<HeroRow[]>('heroes', query).then(
      (found) => current && ((rows = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  // the games and win rate columns draw a bar instead of a text
  const COLUMNS: [string, (r: HeroRow) => number, ((r: HeroRow) => string) | null][] = [
    ['Games', (r) => r.games, null],
    ['Win rate', (r) => r.wins / r.games, null],
    ['Kills', (r) => r.kills, (r) => r.kills.toFixed(1)],
    ['Deaths', (r) => r.deaths, (r) => r.deaths.toFixed(1)],
    ['Assists', (r) => r.assists, (r) => r.assists.toFixed(1)],
    ['GPM', (r) => r.gold_per_min, (r) => r.gold_per_min.toFixed(0)],
    ['XPM', (r) => r.xp_per_min, (r) => r.xp_per_min.toFixed(0)],
  ]
  let sort = $state({ column: 0, descending: true })
  const sorted = $derived(sortedBy(rows, COLUMNS[sort.column][1], sort.descending))
  const sortBy = (column: number) =>
    (sort = { column, descending: sort.column === column ? !sort.descending : true })
  const most = $derived(Math.max(0, ...rows.map((r) => r.games)))
  let unfolded = $state<number[]>([])
  const unfold = (id: number) => (unfolded = unfolded.includes(id) ? unfolded.filter((o) => o !== id) : [...unfolded, id])
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if rows.length === 0}
  <p class="muted">No matches for these filters.</p>
{:else}
  <div class="card tall">
    <table>
      <thead>
        <tr>
          <th></th>
          <th>Hero</th>
          {#each COLUMNS as [title, , text], i}
            <th class:num={text} aria-sort={sort.column === i ? (sort.descending ? 'descending' : 'ascending') : undefined}>
              <button onclick={() => sortBy(i)}>{title}{sort.column === i ? (sort.descending ? ' ↓' : ' ↑') : ''}</button>
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each sorted as r (r.hero_id)}
          {@const open = unfolded.includes(r.hero_id)}
          <tr>
            <td>
              <button class="unfold" aria-expanded={open} aria-label="Matches on {heroName(r.hero_id)}" onclick={() => unfold(r.hero_id)}>{open ? '▾' : '▸'}</button>
            </td>
            <td class="hero"><img src={heroPortrait(r.hero_id)} alt={heroName(r.hero_id)} title={heroName(r.hero_id)} width="44" height="25" loading="lazy" /></td>
            {#each COLUMNS as [, , text], i}
              {#if text}<td class="num">{text(r)}</td>
              {:else if i === 0}<td><Count games={r.games} max={most} /></td>
              {:else}<td><WinRate wins={r.wins} games={r.games} /></td>{/if}
            {/each}
          </tr>
          {#if open}
            <tr class="more">
              <td colspan={COLUMNS.length + 2}><Matches given={matches.filter((m) => m.hero_id === r.hero_id)} /></td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .hero {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .hero img {
    object-fit: cover;
    border-radius: 3px;
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
</style>
