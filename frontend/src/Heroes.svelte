<script lang="ts">
  import { clock, get, sortedBy, type HeroRow, type MatchRow } from './lib/api'
  import { heroName, heroPortrait } from './lib/constants.svelte'
  import Count from './lib/Count.svelte'
  import WinRate from './lib/WinRate.svelte'

  /** `matches` are the profile's matches for the same query, newest first: a hero unfolds into its latest ones */
  let { query, matches }: { query: string; matches: MatchRow[] } = $props()
  const LATEST = 20
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
  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString('en-GB', { dateStyle: 'medium' })
  let unfolded = $state<number[]>([])
  const unfold = (id: number) => (unfolded = unfolded.includes(id) ? unfolded.filter((o) => o !== id) : [...unfolded, id])
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
              <button class="unfold" aria-expanded={open} aria-label="Latest matches on {heroName(r.hero_id)}" onclick={() => unfold(r.hero_id)}>{open ? '▾' : '▸'}</button>
            </td>
            <td class="hero"><img src={heroPortrait(r.hero_id)} alt={heroName(r.hero_id)} title={heroName(r.hero_id)} width="44" height="25" loading="lazy" /></td>
            {#each COLUMNS as [, , text], i}
              {#if text}<td class="num">{text(r)}</td>
              {:else if i === 0}<td><Count games={r.games} max={most} /></td>
              {:else}<td><WinRate wins={r.wins} games={r.games} /></td>{/if}
            {/each}
          </tr>
          {#if open}
            {@const latest = matches.filter((m) => m.hero_id === r.hero_id).slice(0, LATEST)}
            <tr class="more">
              <td colspan={COLUMNS.length + 2}>
                <table>
                  <thead>
                    <tr><th>Date</th><th>Result</th><th class="num">K / D / A</th><th class="num">GPM</th><th class="num">XPM</th><th class="num">LH / DN</th><th class="num">Duration</th></tr>
                  </thead>
                  <tbody>
                    {#each latest as m (m.match_id)}
                      <tr>
                        <td><a href="#match/{m.match_id}">{date(m.start_time)}</a></td>
                        <td><span class="dot {m.win ? 'won' : 'lost'}"></span>{m.win ? 'Won' : 'Lost'}</td>
                        <td class="num">{m.kills} / {m.deaths} / {m.assists}</td>
                        <td class="num">{m.gold_per_min}</td>
                        <td class="num">{m.xp_per_min}</td>
                        <td class="num">{m.last_hits} / {m.denies}</td>
                        <td class="num">{clock(m.duration)}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
                {#if r.games > LATEST}<p class="muted">The latest {LATEST} of {r.games} matches.</p>{/if}
              </td>
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
