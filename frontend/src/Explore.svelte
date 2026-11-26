<script lang="ts">
  import { get } from './lib/api'
  import Calendar from './lib/Calendar.svelte'
  import MatchBoard from './lib/MatchBoard.svelte'
  import TournamentCard from './lib/TournamentCard.svelte'
  import { TIER_GROUPS, tierGroup, type ExploreAnswer, type TierGroup } from './lib/leagues'

  // Explore: the tournament scene at a glance, from what the poller keeps (explore.py); the filters work in the browser
  let found = $state<ExploreAnswer | null>(null)
  let error = $state('')
  get<ExploreAnswer>('explore').then((a) => (found = a), (e) => (error = e.message))
  const now = Date.now() / 1000

  // ---- the filters, kept in this browser
  type Filters = { tiers: TierGroup[]; regions: string[]; place: 'both' | 'online' | 'lan' }
  // a new key when the default changes: every visit saves the filters, so the old key holds the old default
  const KEY = 'explore_filters_2'
  const START: Filters = { tiers: ['1'], regions: [], place: 'both' } // tier 1 until you pick otherwise
  function remembered(): Filters {
    try {
      return { ...START, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
    } catch {
      return { ...START }
    }
  }
  let filters = $state<Filters>(remembered())
  $effect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(filters))
    } catch {
      // a private window: the filters last until the page closes
    }
  })
  const flip = <T,>(list: T[], value: T) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value])
  const REGION_ORDER = ['Europe', 'CIS', 'China', 'SEA', 'North America', 'South America', 'MENA', 'International']
  const regions = $derived(REGION_ORDER.filter((r) => Object.values(found?.leagues ?? {}).some((l) => l.region === r)))
  const filtering = $derived(!!filters.tiers.length || !!filters.regions.length || filters.place !== 'both')

  const league = (id: number) => found?.leagues[String(id)]
  /** Whether a tournament passes the filters; one Explore knows nothing about passes only when nothing is filtered */
  function shown(id: number) {
    const l = league(id)
    if (!l) return !filtering
    if (filters.tiers.length && !filters.tiers.includes(tierGroup(l.lp_tier))) return false
    if (filters.regions.length && !filters.regions.includes(l.region ?? '')) return false
    if (filters.place === 'online' && !l.online) return false
    if (filters.place === 'lan' && (l.online || !l.location)) return false
    return true
  }
  const live = $derived(found?.live.filter((g) => shown(g.league_id)) ?? [])
  const upcoming = $derived(found?.upcoming.filter((m) => shown(m.league_id)) ?? [])
  const results = $derived(found?.results.filter((m) => shown(m.league_id)) ?? [])
  const soon = $derived(found?.soon.filter(shown) ?? [])
  const calendar = $derived(found?.calendar.filter((c) => shown(c.league_id)) ?? [])
  const big = $derived(found?.big.filter(shown) ?? [])
  const finished = $derived(found?.finished.filter((f) => shown(f.league_id)) ?? [])

</script>

{#snippet empty(reason: string)}
  <p class="muted">{filtering ? 'Nothing here matches the filters.' : reason}</p>
{/snippet}

{#if error}<p class="error" role="alert">Explore could not load: {error}</p>{/if}

<div class="chips" role="group" aria-label="Filters">
  <div class="choice" role="group" aria-label="Tier">
    {#each Object.entries(TIER_GROUPS) as [id, name] (id)}
      <button aria-pressed={filters.tiers.includes(id as TierGroup)} onclick={() => (filters.tiers = flip(filters.tiers, id as TierGroup))}>{name}</button>
    {/each}
  </div>
  {#if regions.length}
    <div class="choice" role="group" aria-label="Region">
      {#each regions as r (r)}
        <button aria-pressed={filters.regions.includes(r)} onclick={() => (filters.regions = flip(filters.regions, r))}>{r}</button>
      {/each}
    </div>
  {/if}
  <div class="choice" role="group" aria-label="Online or LAN">
    {#each [['both', 'Online and LAN'], ['online', 'Online'], ['lan', 'LAN']] as [id, name] (id)}
      <button aria-pressed={filters.place === id} onclick={() => (filters.place = id as Filters['place'])}>{name}</button>
    {/each}
  </div>
  {#if filtering}<button class="clear" onclick={() => (filters = { tiers: [], regions: [], place: 'both' })}>Clear filters</button>{/if}
</div>

{#if !found}
  {#if !error}<p class="muted">Loading…</p>{/if}
{:else}
  <MatchBoard
    {live}
    {upcoming}
    {results}
    {league}
    {filtering}
    block="tournaments.explore"
    upcomingTitle="Upcoming in the next 24 hours"
    empty={{
      live: 'No league game is live right now. Steam is asked every 5 minutes.',
      upcoming: 'No match on the brackets read so far starts in the next 24 hours. A few tournaments are read from Liquipedia each poll round.',
      results: "No finished series yet: OpenDota's recent pro games are read every 10 minutes.",
    }}
  />

  <section data-block="tournaments.explore.soon">
    <h2>Starting soon</h2>
    {#if soon.length}
      <div class="grid">{#each soon as id (id)}{@const l = league(id)}{#if l}<TournamentCard league={l} />{/if}{/each}</div>
    {:else}
      {@render empty('No tournament known to Liquipedia starts in the next 14 days.')}
    {/if}
  </section>

  <section data-block="tournaments.explore.calendar">
    <h2>Calendar</h2>
    {#if calendar.length}
      <div class="card pad"><Calendar entries={calendar} {league} {now} /></div>
    {:else}
      {@render empty('No tier 1 to 3 tournament runs in these weeks yet: Liquipedia is asked about a few each poll round.')}
    {/if}
  </section>

  <section data-block="tournaments.explore.big">
    <h2>Biggest of the last 30 days</h2>
    {#if big.length}
      <div class="grid">{#each big as id (id)}{@const l = league(id)}{#if l}<TournamentCard league={l} />{/if}{/each}</div>
    {:else}
      {@render empty("No league played in the last 30 days, or OpenDota's list was not read yet: it is read once a day.")}
    {/if}
  </section>

  <section data-block="tournaments.explore.finished">
    <h2>Recently finished</h2>
    {#if finished.length}
      <div class="grid">
        {#each finished as f (f.league_id)}{@const l = league(f.league_id)}{#if l}<TournamentCard league={l} winner={f.winner} />{/if}{/each}
      </div>
    {:else}
      {@render empty('No tier 1 to 3 tournament ended in the last 30 days.')}
    {/if}
  </section>
{/if}

<style>
  h2 {
    margin: 26px 0 10px;
    font-size: 17px;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 12px;
    margin: 0 0 8px;
  }
  .clear {
    border: 0;
    background: none;
    color: var(--series-1);
    font: inherit;
    cursor: pointer;
  }
  .small {
    font-size: 13px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 10px;
  }
  .pad {
    padding: 10px 14px 12px;
  }
</style>
