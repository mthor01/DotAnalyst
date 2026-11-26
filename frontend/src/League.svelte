<script lang="ts">
  import { get } from './lib/api'
  import { STATUS, dates, day, liquipedia, money, subscribe, tierName, type LeagueGame, type LeaguePage, type Side } from './lib/leagues'

  let { id }: { id: string } = $props()
  let page = $state<LeaguePage | null>(null)
  let error = $state('')
  $effect(() => {
    page = null
    get<LeaguePage>(`leagues/${id}/page`).then((found) => ((page = found), (error = '')), (e) => (error = e.message))
  })
  async function toggle() {
    if (!page) return
    try {
      await subscribe(page.league, !page.league.subscribed)
      page = await get<LeaguePage>(`leagues/${id}/page`) // subscribed, it shows the stored games
    } catch (e) {
      error = (e as Error).message
    }
  }
  const SOURCES = {
    stored: 'the games stored since you subscribed',
    opendota: "OpenDota's list of its games",
    steam: "Steam's list of its games; the newest 20 with teams and result",
    none: '',
  }
  const team = (s: Side) => s.name ?? (s.team_id ? `Team ${s.team_id}` : 'No team')
  const won = (g: LeagueGame, radiant: boolean) => g.radiant_win !== null && g.radiant_win === radiant
  // a subscribed league's games open on the match page and its teams on the team page; others on OpenDota
  const gameLink = (g: LeagueGame) => (page?.subscribed ? `#match/${g.match_id}` : `https://www.opendota.com/matches/${g.match_id}`)
</script>

{#snippet name(s: Side)}
  {#if page?.subscribed && s.team_id}<a href="#team/{s.team_id}">{team(s)}</a>{:else}{team(s)}{/if}
{/snippet}

{#if error}
  <p class="error" role="alert">{error}</p>
{:else if !page}
  <p class="muted">Loading… The first look at an amateur league asks Steam for its games and can take half a minute.</p>
{:else}
  {@const l = page.league}
  <header class="head" data-block="league.header">
    <h2>{l.name}</h2>
    <button class="action" aria-pressed={l.subscribed} onclick={toggle}>{l.subscribed ? 'Subscribed ✓' : 'Subscribe'}</button>
  </header>
  <dl class="card facts" data-block="league.header">
    <div><dt>Status</dt><dd class:live={l.status === 'live'}>{STATUS[l.status]}{l.status === 'live' ? `, ${l.live_games} live` : ''}</dd></div>
    <div><dt>When</dt><dd>{dates(l) || '–'}</dd></div>
    <div><dt>Games</dt><dd>{l.games ?? '–'}</dd></div>
    <div><dt>Tier</dt><dd>{tierName(l.tier)}{l.lp_tier ? `, Liquipedia tier ${l.lp_tier}` : ''}</dd></div>
    {#if l.prize_usd !== null}<div><dt>Prize pool</dt><dd>{money(l.prize_usd)}</dd></div>{/if}
    {#if l.location}<div><dt>Where</dt><dd>{l.location}</dd></div>{/if}
  </dl>
  <p class="muted" data-block="league.header">
    League {l.league_id}.
    {#if l.lp_page}
      <a href={liquipedia(l.lp_page)} target="_blank" rel="noreferrer">On Liquipedia</a>: brackets, standings and more. Prize pool, Liquipedia tier, dates and place from Liquipedia, CC BY-SA 3.0.
    {:else if l.lp_checked}
      Liquipedia has no page for it.
    {/if}
    {#if SOURCES[page.source]}Games from {SOURCES[page.source]}.{/if}
    {#if page.source === 'steam'}Records count only the games with a known result.{/if}
  </p>

  {#if page.games.length === 0}
    <p class="muted">No games known{page.source === 'none' ? ': OpenDota has none, and Steam needs a Steam Web API key to list them (Settings, Fetching)' : ''}.</p>
  {:else}
    <h3 data-block="league.teams">Teams</h3>
    <div class="card" data-block="league.teams">
      <table>
        <thead>
          <tr><th></th><th>Team</th><th class="num">Series won</th><th class="num">Games won</th>{#if page.teams.some((t) => t.rating !== null)}<th class="num">Rating</th>{/if}</tr>
        </thead>
        <tbody>
          {#each page.teams as t (t.team_id)}
            <tr>
              <td class="logo">{#if t.logo}<img src={t.logo} alt={t.name ?? ''} title={t.name ?? ''} width="28" height="28" loading="lazy" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden')} />{/if}</td>
              <td>{@render name({ team_id: t.team_id, name: t.name })}</td>
              <td class="num">{t.series ? `${t.series_wins} / ${t.series}` : '–'}</td>
              <td class="num">{t.games ? `${t.wins} / ${t.games}` : '–'}</td>
              {#if page.teams.some((t) => t.rating !== null)}<td class="num">{t.rating === null ? '' : Math.round(t.rating)}</td>{/if}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <h3 data-block="league.series">Series</h3>
    <div class="card" data-block="league.series">
      <table>
        <thead><tr><th>Day</th><th class="num">Team</th><th class="score">Score</th><th>Team</th><th>Format</th></tr></thead>
        <tbody>
          {#each page.series as s (s.series_id ?? `${s.start_time}`)}
            {@const [a, b] = s.score}
            <tr>
              <td class="muted">{day(s.start_time)}</td>
              <td class="num" class:winner={a > b}>{@render name(s.teams[0])}</td>
              <td class="score">{a} – {b}</td>
              <td class:winner={b > a}>{@render name(s.teams[1])}</td>
              <td class="muted">Bo{s.best_of}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <h3 data-block="league.games">Latest games</h3>
    <div class="card" data-block="league.games">
      <table>
        <thead><tr><th>Day</th><th class="num">Radiant</th><th class="score">Kills</th><th>Dire</th><th></th></tr></thead>
        <tbody>
          {#each page.games.slice(0, 50) as g (g.match_id)}
            <tr>
              <td class="muted">{day(g.start_time)}</td>
              <td class="num" class:winner={won(g, true)}>{@render name(g.radiant)}</td>
              <td class="score">{g.radiant_score ?? '?'} – {g.dire_score ?? '?'}</td>
              <td class:winner={won(g, false)}>{@render name(g.dire)}</td>
              <td class="num"><a href={gameLink(g)} target={page.subscribed ? undefined : '_blank'} rel="noreferrer">{page.subscribed ? 'Open' : 'OpenDota ↗'}</a></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    {#if page.games.length > 50}<p class="muted">The newest 50 of {page.games.length} games.</p>{/if}
  {/if}
{/if}

<style>
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 16px;
  }
  .head h2 {
    margin: 0;
  }
  .head button[aria-pressed='true'] {
    color: var(--text-2);
    background: transparent;
    box-shadow: inset 0 0 0 1px var(--border);
  }
  .facts {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 36px;
    margin: 14px 0 8px;
    padding: 14px 18px;
  }
  .facts dt {
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .facts dd {
    margin: 2px 0 0;
    font-weight: 600;
  }
  .live {
    color: var(--good);
  }
  h3 {
    margin: 22px 0 8px;
  }
  .logo {
    width: 28px;
  }
  .logo img {
    display: block;
    object-fit: contain;
  }
  .score {
    text-align: center;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .winner {
    font-weight: 700;
  }
</style>
