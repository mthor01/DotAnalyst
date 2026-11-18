<script lang="ts">
  import { get, sortedBy, type HeroRow } from './lib/api'
  import { heroName, heroPortrait } from './lib/constants.svelte'
  import WinRate from './lib/WinRate.svelte'

  let { query }: { query: string } = $props()
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

  // the win rate column draws its bar instead of a text
  const COLUMNS: [string, (r: HeroRow) => number, ((r: HeroRow) => string) | null][] = [
    ['Games', (r) => r.games, (r) => String(r.games)],
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
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if rows.length === 0}
  <p class="muted">No matches for these filters.</p>
{:else}
  <div class="card">
    <table>
      <thead>
        <tr>
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
          <tr>
            <td class="hero"><img src={heroPortrait(r.hero_id)} alt="" width="44" height="25" loading="lazy" />{heroName(r.hero_id)}</td>
            {#each COLUMNS as [, , text]}
              {#if text}<td class="num">{text(r)}</td>{:else}<td><WinRate wins={r.wins} games={r.games} /></td>{/if}
            {/each}
          </tr>
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
</style>
