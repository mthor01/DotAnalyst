<script lang="ts">
  import type { Snippet } from 'svelte'
  import { clock } from './api'
  import SeriesGames from './SeriesGames.svelte'
  import type { ExploreLeague, ExploreMatch, ExploreTeam, LiveSeries } from './leagues'

  // Explore's and Home's games: live series across the page, then two columns, the upcoming matches and recent
  // results on the left and the page's own tournaments (`aside`) on the right. `block` names the parts
  // (<block>.live, .upcoming, .results) for the Design settings
  let {
    live, upcoming, results, league, block, upcomingTitle, empty: reasons, filtering = false, aside,
  }: {
    live: LiveSeries[]; upcoming: ExploreMatch[]; results: ExploreMatch[]; league: (id: number | string) => ExploreLeague | undefined
    block: string; upcomingTitle: string; empty: { live: string; upcoming: string; results: string }; filtering?: boolean
    aside: Snippet
  } = $props()

  // a result opens its games; a game opens on the match page of a subscribed league, else OpenDota
  let picked = $state<ExploreMatch | null>(null)
  const gameLink = (matchId: number) =>
    picked && league(picked.league_id)?.subscribed ? `#match/${matchId}` : `https://www.opendota.com/matches/${matchId}`
  const logoOf = (teamId: number) => picked?.opponents.find((o) => o.team_id === teamId)?.logo ?? null
  const leagueName = (id: number, fallback = '') => league(id)?.name ?? fallback

  // rows under a heading per day, in the viewer's time: Today, Tomorrow, Yesterday, else the weekday and date
  const dayKey = (t: number) => new Date(t * 1000).toDateString()
  function dayName(t: number) {
    const day = new Date(t * 1000)
    const offset = Math.round((new Date(day.toDateString()).getTime() - new Date(new Date().toDateString()).getTime()) / 86400000)
    return ({ 0: 'Today', 1: 'Tomorrow', [-1]: 'Yesterday' } as Record<number, string>)[offset]
      ?? day.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short' })
  }
  function byDay(matches: ExploreMatch[]) {
    const days: { name: string; matches: ExploreMatch[] }[] = []
    let last = ''
    for (const m of matches) {
      const key = m.time ? dayKey(m.time) : ''
      if (key !== last || !days.length) days.push({ name: m.time ? dayName(m.time) : 'Date not known', matches: [] })
      days[days.length - 1].matches.push(m)
      last = key
    }
    return days
  }
  const hour = (t: number | null) => (t ? new Date(t * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '')
</script>

{#snippet team(t: Pick<ExploreTeam, 'name' | 'logo'>, left = false)}
  <!-- both names next to the score, the logos outside: [logo] Name 2 : 0 Name [logo] -->
  <span class="team" class:left class:right={!left}>
    {#if t.logo}<img src={t.logo} alt="" width="22" height="22" loading="lazy" />{:else}<span class="nologo"></span>{/if}
    <span class="tname" title={t.name ?? 'To be decided'}>{t.name ?? 'TBD'}</span>
  </span>
{/snippet}

{#snippet empty(reason: string)}
  <p class="muted">{filtering ? 'Nothing here matches the filters.' : reason}</p>
{/snippet}

{#snippet where(m: ExploreMatch)}
  <span class="where">
    <a href="#league/{m.league_id}">{leagueName(m.league_id, m.league_name ?? '')}</a>{#if m.best_of}<span class="bo">Bo{m.best_of}</span>{/if}
  </span>
{/snippet}

<section class="first" data-block="{block}.live">
  <h2>Live now</h2>
  {#if live.length}
    <ul class="live">
      {#each live as g (g.match_id)}
        <li>
          <a href="#league/{g.league_id}">
            <span class="league"><span class="dot-live"></span>{leagueName(g.league_id, `League ${g.league_id}`)}</span>
            <span class="versus">
              <!-- Steam sends no team for a side of players who are no registered team (pickup and lobby leagues) -->
              {@render team({ ...g.radiant, name: g.radiant.name ?? 'Radiant' }, true)}
              <strong class="score">{g.series[0]} : {g.series[1]}</strong>
              {@render team({ ...g.dire, name: g.dire.name ?? 'Dire' })}
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

<div class="split">
  <div class="matches">
    <section data-block="{block}.upcoming">
      <h2>{upcomingTitle}</h2>
      {#if upcoming.length}
        <div class="card list">
          {#each byDay(upcoming) as day (day.name)}
            <h3>{day.name}</h3>
            <ul>
              {#each day.matches as m, i (i)}
                <li>
                  <time>{hour(m.time)}</time>
                  <span class="versus">{@render team(m.opponents[0], true)}<span class="score muted">vs</span>{@render team(m.opponents[1])}</span>
                  {@render where(m)}
                </li>
              {/each}
            </ul>
          {/each}
        </div>
      {:else}
        {@render empty(reasons.upcoming)}
      {/if}
    </section>

    <section data-block="{block}.results">
      <h2>Recent results</h2>
      {#if results.length}
        <div class="card list">
          {#each byDay(results) as day (day.name)}
            <h3>{day.name}</h3>
            <ul>
              {#each day.matches as m, i (i)}
                <li>
                  <time title="When its last game ended">{hour(m.time)}</time>
                  <button class="versus" onclick={() => (picked = m)} title="Show the games">
                    <!-- a team that played without a name is no team to be decided -->
                    <span class:lost={m.winner === 1}>{@render team({ ...m.opponents[0], name: m.opponents[0].name ?? 'Unnamed' }, true)}</span>
                    <strong class="score">{m.score[0]} : {m.score[1]}</strong>
                    <span class:lost={m.winner === 0}>{@render team({ ...m.opponents[1], name: m.opponents[1].name ?? 'Unnamed' })}</span>
                  </button>
                  {@render where(m)}
                </li>
              {/each}
            </ul>
          {/each}
        </div>
      {:else}
        {@render empty(reasons.results)}
      {/if}
    </section>
  </div>
  <aside>{@render aside()}</aside>
</div>

{#if picked}
  <SeriesGames match={picked} logo={logoOf} link={gameLink} onclose={() => (picked = null)} />
{/if}

<style>
  h2 {
    margin: 26px 0 10px;
    font-size: 17px;
  }
  .first h2 {
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
  .league {
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
  .live .score {
    font-size: 22px;
  }
  /* the two columns; one under the other when the page is narrow */
  .split {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
    gap: 0 28px;
    align-items: start;
  }
  @media (max-width: 1000px) {
    .split {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  .matches {
    container-type: inline-size;
    min-width: 0;
  }
  /* a match: time, the teams hugging the score, the tournament at the far end */
  .versus {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .versus > * {
    min-width: 0; /* long names shorten with an ellipsis, not the score */
  }
  .score {
    font-variant-numeric: tabular-nums;
    text-align: center;
    white-space: nowrap;
    min-width: 2.6em;
  }
  .team {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    font-weight: 600;
  }
  .team.left {
    justify-content: flex-end;
  }
  .team.right {
    flex-direction: row-reverse;
    justify-content: flex-end;
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
    opacity: 0.5;
  }
  .list {
    padding: 2px 0 6px;
  }
  .list h3 {
    margin: 0;
    padding: 10px 14px 4px;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
  }
  .list ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .list li {
    display: grid;
    grid-template-columns: 3.4em minmax(0, 1fr) minmax(0, 15em);
    align-items: center;
    gap: 14px;
    padding: 7px 14px;
  }
  .list li:hover {
    background: var(--raised);
  }
  time {
    font-size: 13px;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  button.versus {
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    padding: 2px 0;
    cursor: pointer;
    text-align: inherit;
  }
  button.versus:hover .tname {
    text-decoration: underline;
  }
  .where {
    display: flex;
    justify-content: flex-end;
    align-items: baseline;
    gap: 8px;
    min-width: 0;
    font-size: 13px;
  }
  .where a {
    color: var(--text-2);
    text-decoration: none;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .where a:hover {
    text-decoration: underline;
  }
  .bo {
    flex: none;
    color: var(--muted);
  }
  /* a narrow column: the tournament goes under the teams */
  @container (max-width: 560px) {
    .list li {
      grid-template-columns: 3.4em minmax(0, 1fr);
      gap: 2px 12px;
    }
    .where {
      grid-column: 2;
      justify-content: center;
    }
  }
  /* a phone: the teams take the whole line, the time and the tournament go under them */
  @container (max-width: 420px) {
    .list li {
      grid-template-columns: auto minmax(0, 1fr);
      grid-template-areas: 'versus versus' 'time where';
      gap: 2px 10px;
    }
    .list li > .versus {
      grid-area: versus;
    }
    .list li > time {
      grid-area: time;
    }
    .list li > .where {
      grid-area: where;
      justify-content: flex-start;
    }
  }
</style>
