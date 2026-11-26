<script lang="ts">
  import { get } from './lib/api'
  import Bracket from './lib/Bracket.svelte'
  import { heroIcon, heroName } from './lib/constants.svelte'
  import {
    STATUS, dates, day, liquipedia, moment, money, subscribe, tierName,
    type HeadToHead, type LeagueGame, type LeaguePage, type LpMatch, type LpOpponent, type Record_, type Side,
  } from './lib/leagues'
  import { shownTab } from './lib/settings.svelte'

  let { id, tab = '' }: { id: string; tab?: string } = $props()
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

  // the tabs by their Design id, #league/<id>/<tab>; a hidden tab gives way
  const TABS = { overview: 'Overview', teams: 'Teams', stats: 'Stats', games: 'Games' }
  type Tab = keyof typeof TABS
  const shown = $derived(shownTab('league', Object.keys(TABS) as Tab[], tab in TABS ? (tab as Tab) : 'overview'))

  const SOURCES = {
    stored: 'the games stored since you subscribed',
    opendota: "OpenDota's list of its games",
    steam: "Steam's list of its games; the newest 20 with teams and result",
    none: '',
  }
  const team = (s: Side) => s.name ?? (s.team_id ? `Team ${s.team_id}` : 'No team')
  const won = (g: LeagueGame, radiant: boolean) => g.radiant_win !== null && g.radiant_win === radiant
  // a subscribed league's games open on the match page and its teams on the team page; others on OpenDota
  const gameLink = (matchId: number) => (page?.subscribed ? `#match/${matchId}` : `https://www.opendota.com/matches/${matchId}`)
  const logos = $derived(new Map(page?.teams.map((t) => [t.team_id, t.logo]) ?? []))
  const logo = (teamId: number) => logos.get(teamId) ?? null
  const matchLink = (m: LpMatch) => {
    const played = m.maps.find((p) => p.match_id && p.winner !== null)?.match_id ?? null
    return played ? gameLink(played) : null
  }
  const percent = (x: number) => `${Math.round(x * 100)}%`
  const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

  // ---- Teams: a row opens its roster, Liquipedia's (by team or name) else the players seen in the stored games
  let open = $state<Set<number>>(new Set())
  const flip = (teamId: number) => (open = open.has(teamId) ? new Set([...open].filter((t) => t !== teamId)) : new Set([...open, teamId]))
  const lpRoster = (teamId: number, name: string | null) =>
    page?.liquipedia?.rosters.find((r) => (r.team_id && r.team_id === teamId) || (name && r.name.toLowerCase() === name.toLowerCase()))

  // ---- Stats: sortable tables, as on the Heroes tab
  type H = NonNullable<LeaguePage['heroes']>[number]
  const HERO_SORTS = { picks: (h: H) => h.picks, wins: (h: H) => (h.picks ? h.wins / h.picks : -1), bans: (h: H) => h.bans, contested: (h: H) => h.contested }
  type HeroKey = keyof typeof HERO_SORTS
  let heroSort = $state<{ key: HeroKey; down: boolean }>({ key: 'contested', down: true })
  const heroes = $derived.by(() => {
    const { key, down } = heroSort
    return [...(page?.heroes ?? [])].sort((a, b) => (down ? HERO_SORTS[key](b) - HERO_SORTS[key](a) : HERO_SORTS[key](a) - HERO_SORTS[key](b)))
  })
  type P = NonNullable<LeaguePage['players']>[number]
  const PLAYER_SORTS = {
    games: (p: P) => p.games, wins: (p: P) => p.wins / p.games, kda: (p: P) => p.kda, kills: (p: P) => p.kills, deaths: (p: P) => p.deaths,
    assists: (p: P) => p.assists, gpm: (p: P) => p.gpm, xpm: (p: P) => p.xpm, last_hits: (p: P) => p.last_hits, hero_damage: (p: P) => p.hero_damage,
  }
  type PlayerKey = keyof typeof PLAYER_SORTS
  let playerSort = $state<{ key: PlayerKey; down: boolean }>({ key: 'games', down: true })
  const players = $derived.by(() => {
    const { key, down } = playerSort
    return [...(page?.players ?? [])].sort((a, b) => (down ? PLAYER_SORTS[key](b) - PLAYER_SORTS[key](a) : PLAYER_SORTS[key](a) - PLAYER_SORTS[key](b)) || b.games - a.games)
  })

  // ---- Head-to-head: two of the league's teams, over every stored league game
  let pair = $state<[number, number]>([0, 0])
  $effect(() => {
    const ids = page?.teams.map((t) => t.team_id) ?? []
    if (ids.length >= 2 && !(ids.includes(pair[0]) && ids.includes(pair[1]))) pair = [ids[0], ids[1]]
  })
  let versus = $state<HeadToHead | null>(null)
  $effect(() => {
    const [a, b] = pair
    versus = null
    if (shown === 'stats' && page?.subscribed && a && b && a !== b)
      get<HeadToHead>(`teams/${a}/vs/${b}`).then((found) => (versus = found), (e) => (error = e.message))
  })
</script>

{#snippet name(s: Side)}
  {#if page?.subscribed && s.team_id}<a href="#team/{s.team_id}">{team(s)}</a>{:else}{team(s)}{/if}
{/snippet}

{#snippet badge(teamId: number, label: string | null)}
  {@const src = teamId ? logo(teamId) : null}
  <span class="badge">
    <span class="logo-s">{#if src}<img {src} alt="" width="20" height="20" loading="lazy" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden')} />{/if}</span>
    {@render name({ team_id: teamId, name: label })}
  </span>
{/snippet}

{#snippet opponent(o: LpOpponent)}
  {#if o.name}{@render badge(o.team_id, o.name)}{:else}<span class="muted">TBD</span>{/if}
{/snippet}

{#snippet sortable(label: string, key: string, sort: { key: string; down: boolean }, set: (s: { key: any; down: boolean }) => void)}
  <th class="num" aria-sort={sort.key === key ? (sort.down ? 'descending' : 'ascending') : undefined}>
    <button onclick={() => set({ key, down: sort.key === key ? !sort.down : true })}>
      {label}<span class="arrow" aria-hidden="true">{sort.key === key ? (sort.down ? '▾' : '▴') : ''}</span>
    </button>
  </th>
{/snippet}

{#snippet table(rows: Record_[])}
  <div class="card">
    <table>
      <thead><tr><th class="num">#</th><th>Team</th><th class="num">Series</th><th class="num">Maps</th><th class="num">Map diff</th></tr></thead>
      <tbody>
        {#each rows as r, i (r.team_id || r.name)}
          <tr>
            <td class="num muted">{i + 1}</td>
            <td>{@render badge(r.team_id, r.name)}</td>
            <td class="num">{r.series_wins} – {r.series_losses}</td>
            <td class="num">{r.map_wins} – {r.map_losses}</td>
            <td class="num">{r.map_wins - r.map_losses > 0 ? '+' : ''}{r.map_wins - r.map_losses}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/snippet}

{#if error}
  <p class="error" role="alert">{error}</p>
{/if}
{#if !page}
  {#if !error}<p class="muted">Loading… The first look at an amateur league asks Steam for its games and can take half a minute.</p>{/if}
{:else}
  {@const l = page.league}
  {@const lp = page.liquipedia}
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
      <a href={liquipedia(l.lp_page)} target="_blank" rel="noreferrer">On Liquipedia</a>. Brackets, groups, upcoming matches, rosters, prize pool, tier, dates and place from Liquipedia, CC BY-SA 3.0.
    {:else if l.lp_checked}
      Liquipedia has no page for it.
    {/if}
    {#if SOURCES[page.source]}Games from {SOURCES[page.source]}.{/if}
  </p>

  <div class="choice tabs" role="group" aria-label="Part of the tournament page">
    {#each Object.entries(TABS) as [tabId, title]}
      <button data-block="league.{tabId}" aria-pressed={shown === tabId} onclick={() => (location.hash = tabId === 'overview' ? `league/${id}` : `league/${id}/${tabId}`)}>{title}</button>
    {/each}
  </div>

  {#if shown === 'overview'}
    {#if page.live.length}
      <section data-block="league.overview.live">
        <h3>Live now</h3>
        <ul class="cards">
          {#each page.live as g (g.match_id)}
            <li class="card match-card">
              <span class="live">● Live</span>
              {@render badge(g.radiant.team_id, g.radiant.name)}
              <span class="vs">{g.series[0]} – {g.series[1]}</span>
              {@render badge(g.dire.team_id, g.dire.name)}
              <span class="muted">Bo{g.best_of}{g.duration ? ` · ${clock(g.duration)}` : ''}{g.score[0] !== null ? ` · kills ${g.score[0]}–${g.score[1]}` : ''}</span>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
    {#if lp?.upcoming.length}
      <section data-block="league.overview.upcoming">
        <h3>Upcoming</h3>
        <ul class="cards">
          {#each lp.upcoming as m, i (i)}
            <li class="card match-card">
              <span class="muted when">{m.time ? moment(m.time) : ''}</span>
              {@render opponent(m.opponents[0])}
              <span class="vs">vs</span>
              {@render opponent(m.opponents[1])}
            </li>
          {/each}
        </ul>
      </section>
    {/if}
    {#if lp?.brackets.length}
      <section data-block="league.overview.bracket">
        {#each lp.brackets as b, i (i)}
          <h3>{b.title}</h3>
          <div class="card bracket"><Bracket bracket={b} {logo} link={matchLink} /></div>
        {/each}
      </section>
    {/if}
    <section data-block="league.overview.groups">
      {#if lp?.groups.length}
        <div class="groups">
          {#each lp.groups as g, i (i)}
            <div><h3>{g.title}</h3>{@render table(g.rows)}</div>
          {/each}
        </div>
      {:else if page.standings.length}
        <h3>Standings</h3>
        <p class="muted">Worked out from the series results{lp ? '' : ': Liquipedia has no groups of this league'}. Series, then maps, then map difference.</p>
        {@render table(page.standings)}
      {/if}
    </section>
    {#if !page.live.length && !lp?.upcoming.length && !lp?.brackets.length && !lp?.groups.length && !page.standings.length}
      <p class="muted">No games known{page.source === 'none' ? ': OpenDota has none, and Steam needs a Steam Web API key to list them (Settings, Fetching)' : ''}.</p>
    {/if}
  {:else if shown === 'teams'}
    <section data-block="league.teams">
      {#if page.teams.length === 0}
        <p class="muted">No teams known yet.</p>
      {:else}
        {#if page.source === 'steam'}<p class="muted">Records count only the games with a known result.</p>{/if}
        <div class="card">
          <table>
            <thead>
              <tr><th></th><th>Team</th><th class="num">Series won</th><th class="num">Games won</th>{#if page.teams.some((t) => t.rating !== null)}<th class="num">Rating</th>{/if}<th></th></tr>
            </thead>
            <tbody>
              {#each page.teams as t (t.team_id)}
                {@const fromLp = lpRoster(t.team_id, t.name)}
                {@const played = page.rosters?.[String(t.team_id)] ?? []}
                <tr>
                  <td class="logo">{#if t.logo}<img src={t.logo} alt={t.name ?? ''} title={t.name ?? ''} width="28" height="28" loading="lazy" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden')} />{/if}</td>
                  <td>{@render name({ team_id: t.team_id, name: t.name })}</td>
                  <td class="num">{t.series ? `${t.series_wins} / ${t.series}` : '–'}</td>
                  <td class="num">{t.games ? `${t.wins} / ${t.games}` : '–'}</td>
                  {#if page.teams.some((t) => t.rating !== null)}<td class="num">{t.rating === null ? '' : Math.round(t.rating)}</td>{/if}
                  <td class="num">
                    {#if fromLp?.players.length || played.length}
                      <button class="link" aria-expanded={open.has(t.team_id)} onclick={() => flip(t.team_id)}>{open.has(t.team_id) ? 'Hide roster' : 'Roster'}</button>
                    {/if}
                  </td>
                </tr>
                {#if open.has(t.team_id)}
                  <tr class="roster">
                    <td></td>
                    <td colspan="5">
                      {#if fromLp?.players.length}
                        <ul class="people">
                          {#each fromLp.players as p (p.handle)}
                            <li>{p.handle}{#if p.role}<span class="muted"> · pos {p.role}</span>{/if}{#if p.sub}<span class="muted"> · stand-in</span>{/if}</li>
                          {/each}
                        </ul>
                        <p class="muted">From Liquipedia.</p>
                      {:else}
                        <ul class="people">
                          {#each played as p (p.account_id)}
                            <li>
                              {#if p.avatar}<img class="avatar" src={p.avatar} alt="" width="20" height="20" loading="lazy" />{/if}
                              {p.name ?? `Player ${p.account_id}`}<span class="muted"> · {p.games} {p.games === 1 ? 'game' : 'games'}</span>
                            </li>
                          {/each}
                        </ul>
                        <p class="muted">The players seen playing for it in the stored games.</p>
                      {/if}
                    </td>
                  </tr>
                {/if}
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </section>
  {:else if shown === 'stats'}
    {#if !page.subscribed}
      <p class="muted">Subscribe to see the heroes, players and head-to-head of this tournament: they come from its stored games, with every player's hero and numbers.</p>
    {:else}
      <section data-block="league.stats.heroes">
        <h3>Heroes</h3>
        <p class="muted">Contested: picked or banned, of the games with a draft.</p>
        <div class="card">
          <table>
            <thead>
              <tr>
                <th>Hero</th>
                {@render sortable('Picks', 'picks', heroSort, (s) => (heroSort = s))}
                {@render sortable('Win rate', 'wins', heroSort, (s) => (heroSort = s))}
                {@render sortable('Bans', 'bans', heroSort, (s) => (heroSort = s))}
                {@render sortable('Contested', 'contested', heroSort, (s) => (heroSort = s))}
              </tr>
            </thead>
            <tbody>
              {#each heroes as h (h.hero_id)}
                <tr>
                  <td><img class="hero" src={heroIcon(h.hero_id)} alt={heroName(h.hero_id)} title={heroName(h.hero_id)} width="32" height="32" loading="lazy" /></td>
                  <td class="num">{h.picks}</td>
                  <td class="num">{h.picks ? percent(h.wins / h.picks) : '–'}</td>
                  <td class="num">{h.bans}</td>
                  <td class="num">{percent(h.contested)}</td>
                </tr>
              {:else}
                <tr><td colspan="5" class="muted">No drafts stored.</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
      <section data-block="league.stats.players">
        <h3>Players</h3>
        <div class="card wide">
          <table>
            <thead>
              <tr>
                <th>Player</th><th>Heroes</th>
                {@render sortable('Games', 'games', playerSort, (s) => (playerSort = s))}
                {@render sortable('Win rate', 'wins', playerSort, (s) => (playerSort = s))}
                {@render sortable('K', 'kills', playerSort, (s) => (playerSort = s))}
                {@render sortable('D', 'deaths', playerSort, (s) => (playerSort = s))}
                {@render sortable('A', 'assists', playerSort, (s) => (playerSort = s))}
                {@render sortable('KDA', 'kda', playerSort, (s) => (playerSort = s))}
                {@render sortable('GPM', 'gpm', playerSort, (s) => (playerSort = s))}
                {@render sortable('XPM', 'xpm', playerSort, (s) => (playerSort = s))}
                {@render sortable('LH', 'last_hits', playerSort, (s) => (playerSort = s))}
                {@render sortable('Damage', 'hero_damage', playerSort, (s) => (playerSort = s))}
              </tr>
            </thead>
            <tbody>
              {#each players as p (p.account_id)}
                <tr>
                  <td>
                    <span class="player">
                      <span class="logo-s">{#if logo(p.team_id)}<img src={logo(p.team_id)} alt="" width="20" height="20" loading="lazy" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden')} />{/if}</span>
                      {p.name ?? `Player ${p.account_id}`}
                    </span>
                  </td>
                  <td class="icons">
                    {#each p.heroes as h (h)}<img src={heroIcon(h)} alt={heroName(h)} title={heroName(h)} width="24" height="24" loading="lazy" />{/each}
                  </td>
                  <td class="num">{p.games}</td>
                  <td class="num">{percent(p.wins / p.games)}</td>
                  <td class="num">{p.kills}</td>
                  <td class="num">{p.deaths}</td>
                  <td class="num">{p.assists}</td>
                  <td class="num">{p.kda}</td>
                  <td class="num">{Math.round(p.gpm)}</td>
                  <td class="num">{Math.round(p.xpm)}</td>
                  <td class="num">{Math.round(p.last_hits)}</td>
                  <td class="num">{Math.round(p.hero_damage).toLocaleString('en-US')}</td>
                </tr>
              {:else}
                <tr><td colspan="12" class="muted">No players stored.</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
      {#if page.teams.length >= 2}
        <section data-block="league.stats.h2h">
          <h3>Head-to-head</h3>
          <form class="filters" onsubmit={(e) => e.preventDefault()}>
            {#each [0, 1] as i}
              <label>
                {i === 0 ? 'Team' : 'against'}
                <select bind:value={pair[i]}>
                  {#each page.teams as t (t.team_id)}<option value={t.team_id}>{t.name ?? `Team ${t.team_id}`}</option>{/each}
                </select>
              </label>
            {/each}
          </form>
          {#if pair[0] === pair[1]}
            <p class="muted">Pick two different teams.</p>
          {:else if versus}
            <p class="record">
              {@render badge(versus.teams[0].team_id, versus.teams[0].name)}
              <strong>{versus.wins[0]} – {versus.wins[1]}</strong>
              {@render badge(versus.teams[1].team_id, versus.teams[1].name)}
              <span class="muted">in {versus.games} {versus.games === 1 ? 'game' : 'games'} of every subscribed tournament</span>
            </p>
            {#if versus.series.length}
              <div class="card">
                <table>
                  <thead><tr><th>Day</th><th>Tournament</th><th class="score">Score</th></tr></thead>
                  <tbody>
                    {#each versus.series as s, i (i)}
                      <tr>
                        <td class="muted">{day(s.start_time)}</td>
                        <td><a href="#league/{s.league_id}">{s.league_name ?? `League ${s.league_id}`}</a></td>
                        <td class="score">{s.score[0]} – {s.score[1]}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
          {/if}
        </section>
      {/if}
    {/if}
  {:else}
    {#if page.games.length === 0}
      <p class="muted">No games known{page.source === 'none' ? ': OpenDota has none, and Steam needs a Steam Web API key to list them (Settings, Fetching)' : ''}.</p>
    {:else}
      <section data-block="league.games.series">
        <h3>Series</h3>
        <div class="card">
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
      </section>
      <section data-block="league.games.latest">
        <h3>Latest games</h3>
        <div class="card">
          <table>
            <thead><tr><th>Day</th><th class="num">Radiant</th><th class="score">Kills</th><th>Dire</th><th></th></tr></thead>
            <tbody>
              {#each page.games.slice(0, 50) as g (g.match_id)}
                <tr>
                  <td class="muted">{day(g.start_time)}</td>
                  <td class="num" class:winner={won(g, true)}>{@render name(g.radiant)}</td>
                  <td class="score">{g.radiant_score ?? '?'} – {g.dire_score ?? '?'}</td>
                  <td class:winner={won(g, false)}>{@render name(g.dire)}</td>
                  <td class="num"><a href={gameLink(g.match_id)} target={page.subscribed ? undefined : '_blank'} rel="noreferrer">{page.subscribed ? 'Open' : 'OpenDota ↗'}</a></td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#if page.games.length > 50}<p class="muted">The newest 50 of {page.games.length} games.</p>{/if}
      </section>
    {/if}
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
  .tabs {
    margin: 14px 0 4px;
  }
  .live {
    color: var(--good);
    font-weight: 600;
  }
  h3 {
    margin: 22px 0 8px;
  }
  .cards {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .match-card {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 12px;
    padding: 10px 14px;
  }
  .when {
    min-width: 7.5em;
  }
  .vs {
    font-variant-numeric: tabular-nums;
    font-weight: 700;
  }
  .badge,
  .player {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .logo-s {
    display: inline-block;
    width: 20px;
    height: 20px;
    flex: none;
  }
  .logo-s img,
  .logo img {
    display: block;
    object-fit: contain;
  }
  .logo {
    width: 28px;
  }
  .bracket {
    padding: 12px 14px;
  }
  .groups {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr));
    gap: 0 18px;
  }
  .roster td {
    padding-top: 0;
  }
  .people {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 18px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .people li {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .avatar {
    border-radius: 50%;
  }
  .people + p {
    margin: 6px 0 0;
    font-size: 12px;
  }
  button.link {
    padding: 0;
    border: 0;
    background: none;
    color: var(--series-1);
    cursor: pointer;
    font: inherit;
  }
  .hero {
    display: block;
  }
  .icons {
    white-space: nowrap;
  }
  .icons img {
    vertical-align: middle;
    margin-right: 2px;
  }
  .wide {
    overflow-x: auto;
  }
  .record {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 12px;
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
