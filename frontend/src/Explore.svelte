<script lang="ts">
  import { clock, get } from './lib/api'
  import Calendar from './lib/Calendar.svelte'
  import SeriesGames from './lib/SeriesGames.svelte'
  import TournamentCard from './lib/TournamentCard.svelte'
  import { TIER_GROUPS, moment, tierGroup, type ExploreAnswer, type ExploreMatch, type ExploreTeam, type TierGroup } from './lib/leagues'

  // Explore: the tournament scene at a glance, from what the poller keeps (explore.py); the filters work in the browser
  let found = $state<ExploreAnswer | null>(null)
  let error = $state('')
  get<ExploreAnswer>('explore').then((a) => (found = a), (e) => (error = e.message))
  const now = Date.now() / 1000

  // ---- the filters, kept in this browser
  type Filters = { tiers: TierGroup[]; regions: string[]; place: 'both' | 'online' | 'lan' }
  const KEY = 'explore_filters'
  function remembered(): Filters {
    try {
      return { tiers: [], regions: [], place: 'both', ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
    } catch {
      return { tiers: [], regions: [], place: 'both' }
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

  // ---- a result opens its games; a game opens on the match page of a subscribed league, else OpenDota
  let picked = $state<ExploreMatch | null>(null)
  const gameLink = (matchId: number) =>
    picked && league(picked.league_id)?.subscribed ? `#match/${matchId}` : `https://www.opendota.com/matches/${matchId}`
  const logoOf = (teamId: number) => picked?.opponents.find((o) => o.team_id === teamId)?.logo ?? null
  const leagueName = (id: number, fallback = '') => league(id)?.name ?? fallback
  const ago = (t: number) => {
    const minutes = Math.max(1, Math.round((now - t) / 60))
    return minutes < 60 ? `${minutes} min ago` : minutes < 48 * 60 ? `${Math.round(minutes / 60)} h ago` : `${Math.round(minutes / 1440)} days ago`
  }
</script>

{#snippet team(t: Pick<ExploreTeam, 'name' | 'logo'>, end = false)}
  <span class="team" class:end>
    {#if t.logo}<img src={t.logo} alt="" width="22" height="22" loading="lazy" />{:else}<span class="nologo"></span>{/if}
    <span class="tname" title={t.name ?? 'To be decided'}>{t.name ?? 'TBD'}</span>
  </span>
{/snippet}

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
  <section data-block="tournaments.explore.live">
    <h2>Live now</h2>
    {#if live.length}
      <ul class="live">
        {#each live as g (g.match_id)}
          <li>
            <a href="#league/{g.league_id}">
              <span class="where"><span class="dot-live"></span>{leagueName(g.league_id, `League ${g.league_id}`)}</span>
              <span class="versus">
                {@render team({ ...g.radiant, name: g.radiant.name ?? 'Radiant' })}
                <strong class="series">{g.series[0]} : {g.series[1]}</strong>
                {@render team({ ...g.dire, name: g.dire.name ?? 'Dire' }, true)}
              </span>
              <span class="muted small">
                Bo{g.best_of}{#if g.duration !== null}, game {g.series[0] + g.series[1] + 1} at {clock(Math.floor(g.duration))}{/if}{#if g.score[0] !== null}, kills {g.score[0]} – {g.score[1]}{/if}
              </span>
            </a>
          </li>
        {/each}
      </ul>
    {:else}
      {@render empty('No league game is live right now. Steam is asked every 5 minutes.')}
    {/if}
  </section>

  <section data-block="tournaments.explore.upcoming">
    <h2>Upcoming in the next 24 hours</h2>
    {#if upcoming.length}
      <ul class="rows card">
        {#each upcoming as m, i (i)}
          <li>
            <span class="when">{m.time ? moment(m.time) : ''}</span>
            <span class="versus">{@render team(m.opponents[0])}<span class="muted">vs</span>{@render team(m.opponents[1], true)}</span>
            <span class="muted small">{m.best_of ? `Bo${m.best_of}` : ''}</span>
            <a class="small" href="#league/{m.league_id}">{leagueName(m.league_id)}</a>
          </li>
        {/each}
      </ul>
    {:else}
      {@render empty('No match on the brackets read so far starts in the next 24 hours. A few tournaments are read from Liquipedia each poll round.')}
    {/if}
  </section>

  <section data-block="tournaments.explore.results">
    <h2>Recent results</h2>
    {#if results.length}
      <ul class="rows card">
        {#each results as m, i (i)}
          <li>
            <span class="when muted">{m.time ? ago(m.time) : ''}</span>
            <button class="versus" onclick={() => (picked = m)} title="Show the games">
              <span class:lost={m.winner === 1}>{@render team(m.opponents[0])}</span>
              <strong class="series">{m.score[0]} : {m.score[1]}</strong>
              <span class:lost={m.winner === 0}>{@render team(m.opponents[1], true)}</span>
            </button>
            <span class="muted small">Bo{m.best_of}</span>
            <a class="small" href="#league/{m.league_id}">{leagueName(m.league_id, m.league_name ?? '')}</a>
          </li>
        {/each}
      </ul>
    {:else}
      {@render empty("No finished series yet: OpenDota's recent pro games are read every 10 minutes.")}
    {/if}
  </section>

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

{#if picked}
  <SeriesGames match={picked} logo={logoOf} link={gameLink} onclose={() => (picked = null)} />
{/if}

<style>
  h2 {
    margin: 26px 0 10px;
    font-size: 17px;
  }
  section:first-of-type h2 {
    margin-top: 6px;
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
  /* live: the one place with weight, a score you read across the room */
  .live {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 10px;
  }
  .live a {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px 14px 12px;
    border-radius: 6px;
    background: var(--surface);
    color: var(--text);
    text-decoration: none;
  }
  .live a:hover {
    background: var(--raised);
  }
  .where {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 13px;
    color: var(--text-2);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .dot-live {
    flex: none;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--good);
    animation: pulse 1.6s ease-in-out infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.3;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .dot-live {
      animation: none;
    }
  }
  .live .series {
    font-size: 22px;
  }
  .versus {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .series {
    font-variant-numeric: tabular-nums;
    text-align: center;
  }
  .team {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    font-weight: 600;
  }
  .team.end {
    flex-direction: row-reverse;
  }
  .team img {
    flex: none;
    object-fit: contain;
  }
  .nologo {
    flex: none;
    width: 22px;
  }
  .tname {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .lost {
    opacity: 0.55;
  }
  /* upcoming and results: rows, so a long day stays one glance */
  .rows {
    list-style: none;
    margin: 0;
    padding: 4px 0;
  }
  .rows li {
    display: grid;
    grid-template-columns: 9em minmax(0, 26em) 3em minmax(0, 1fr);
    align-items: center;
    gap: 12px;
    padding: 6px 14px;
  }
  .rows li + li {
    border-top: 1px solid var(--border);
  }
  .rows .when {
    font-size: 13px;
    font-variant-numeric: tabular-nums;
  }
  .rows button.versus {
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    padding: 2px 0;
    cursor: pointer;
    text-align: inherit;
  }
  .rows button.versus:hover .tname {
    text-decoration: underline;
  }
  .rows a {
    color: var(--text-2);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  @media (max-width: 700px) {
    .rows li {
      grid-template-columns: 1fr auto;
      gap: 4px 10px;
    }
    .rows .versus {
      grid-column: 1 / -1;
      grid-row: 2;
    }
  }
</style>
