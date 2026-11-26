<script lang="ts">
  import { clock } from './api'
  import SeriesGames from './SeriesGames.svelte'
  import { moment, type ExploreLeague, type ExploreMatch, type ExploreTeam, type LiveSeries } from './leagues'

  // live series, upcoming matches and recent results, as Explore and Home show them; `block` names their parts
  // (<block>.live, .upcoming, .results) for the Design settings
  let {
    live, upcoming, results, league, block, upcomingTitle, empty: reasons, filtering = false,
  }: {
    live: LiveSeries[]; upcoming: ExploreMatch[]; results: ExploreMatch[]; league: (id: number) => ExploreLeague | undefined
    block: string; upcomingTitle: string; empty: { live: string; upcoming: string; results: string }; filtering?: boolean
  } = $props()
  const now = Date.now() / 1000

  // a result opens its games; a game opens on the match page of a subscribed league, else OpenDota
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

<section data-block="{block}.live">
  <h2>Live now</h2>
  {#if live.length}
    <ul class="live">
      {#each live as g (g.match_id)}
        <li>
          <a href="#league/{g.league_id}">
            <span class="where"><span class="dot-live"></span>{leagueName(g.league_id, `League ${g.league_id}`)}</span>
            <span class="versus">
              <!-- Steam sends no team for a side of players who are no registered team (pickup and lobby leagues) -->
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
    {@render empty(reasons.live)}
  {/if}
</section>

<section data-block="{block}.upcoming">
  <h2>{upcomingTitle}</h2>
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
    {@render empty(reasons.upcoming)}
  {/if}
</section>

<section data-block="{block}.results">
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
          <span class="muted small">{m.best_of ? `Bo${m.best_of}` : ''}</span>
          <a class="small" href="#league/{m.league_id}">{leagueName(m.league_id, m.league_name ?? '')}</a>
        </li>
      {/each}
    </ul>
  {:else}
    {@render empty(reasons.results)}
  {/if}
</section>

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
  .small {
    font-size: 13px;
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
  .versus > * {
    min-width: 0; /* long names shorten with an ellipsis, not the score */
  }
  .series {
    font-variant-numeric: tabular-nums;
    text-align: center;
    white-space: nowrap;
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
