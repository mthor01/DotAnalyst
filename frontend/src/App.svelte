<script lang="ts">
  import { GAME_MODES, LOBBY_TYPES, get, post, type Account } from './lib/api'
  import { MARKS } from './lib/RoleWheel.svelte'
  import { constants, heroIcon, heroName, loadConstants } from './lib/constants.svelte'
  import Match from './Match.svelte'
  import Compare from './Compare.svelte'
  import Profile from './Profile.svelte'
  import Progress from './lib/Progress.svelte'
  import Queue from './Queue.svelte'
  import Team from './Team.svelte'
  import League from './League.svelte'
  import Tournaments from './Tournaments.svelte'
  import Settings from './Settings.svelte'
  import { hiddenIds, isHidden, loadSettings, prefs, type Settings as Values } from './lib/settings.svelte'

  const PAGES = { profile: 'Profile', compare: 'Player comparison', tournaments: 'Tournaments', queue: 'Queue', settings: 'Settings' }
  const NAV: Page[] = ['profile', 'compare', 'tournaments'] // the page tabs; the progress bar opens Queue, the gear Settings
  const ALL_ACCOUNTS: Page[] = ['compare'] // these pages show every tracked account at once
  type Page = keyof typeof PAGES
  let hash = $state(location.hash.slice(1))
  // with no page in the address, the first page the Design settings leave shown
  const page = $derived<Page>(hash.split('/')[0] in PAGES ? (hash.split('/')[0] as Page) : (NAV.find((id) => !isHidden(id)) ?? 'profile'))
  const settingsTab = $derived(/^settings\/(\w+)$/.exec(hash)?.[1] ?? '') // #settings/data is its Data tab
  const profileTab = $derived(/^profile\/(\w+)$/.exec(hash)?.[1] ?? '') // #profile/matches is a tab of the profile
  const matchId = $derived(/^match\/(\d+)$/.exec(hash)?.[1]) // #match/123 is one match, outside the pages above
  const teamId = $derived(/^team\/(\d+)$/.exec(hash)?.[1]) // #team/123 is one league team, under Tournaments
  const leagueRoute = $derived(/^league\/(\d+)(?:\/(\w+))?$/.exec(hash)) // #league/123[/tab] is one tournament, under Tournaments
  const leagueId = $derived(leagueRoute?.[1])
  const tournamentsTab = $derived(/^tournaments\/(\w+)$/.exec(hash)?.[1] ?? '') // #tournaments/teams is its Teams tab
  // the league pages are about other people's games: no account and none of the filters apply
  const league = $derived(!!teamId || !!leagueId || (!matchId && page === 'tournaments'))
  let accounts = $state<Account[]>([])
  let error = $state('')
  let filters = $state({ account_id: '', lobby_type: '', game_mode: '', hero_id: '' })
  // a number is that many months back from today; only "dates" uses the From and To days
  // a Map: an object puts the numeric keys first, whatever order they are written in, and All time goes top left
  const SPANS = new Map([['all', 'All time'], ['1', 'Last month'], ['3', 'Last 3 months'], ['6', 'Last 6 months'], ['12', 'Last year'], ['dates', 'Dates…']])
  // season and time: the team pages keep their own, so a team's season does not narrow the profile
  const times = $state({
    player: { league_id: '', span: 'all', date_from: '', date_to: '' },
    team: { league_id: '', span: 'all', date_from: '', date_to: '' },
  })
  const time = $derived(league ? times.team : times.player)
  // the player's own filters, sent as position, party and last; the league pages have none of them
  const SIZES = [25, 100, 500, 0] // 0: every match
  /** The role picker: a short name, a long one and the positions it takes in (see Position 1–5 in IMPLEMENTATION.md) */
  const ROLES: [string, string, (1 | 2 | 3 | 4 | 5)[]][] = [
    ['All', 'Every role', []],
    ['1', 'Pos 1 (carry)', [1]],
    ['2', 'Pos 2 (mid)', [2]],
    ['3', 'Pos 3 (offlane)', [3]],
    ['4', 'Pos 4 (soft support)', [4]],
    ['5', 'Pos 5 (hard support)', [5]],
    ['Cores', 'Cores (pos 1–3)', [1, 2, 3]],
    ['Supports', 'Supports (pos 4–5)', [4, 5]],
  ]
  const QUEUES = ['Both', 'Solo', 'Party'] // see Solo or party in IMPLEMENTATION.md
  const own = $state({ size: 100, role: 0, queue: 0 })
  // the hero filter offers only the heroes played: the account's, or every account's on the pages that show them all
  const heroes = $derived(
    ALL_ACCOUNTS.includes(page)
      ? [...new Set(accounts.flatMap((a) => a.heroes))]
      : (accounts.find((a) => String(a.account_id) === filters.account_id)?.heroes ?? []),
  )
  // another account may never have played the picked hero: its grid has no button to take it back off
  $effect(() => {
    if (filters.hero_id && !heroes.includes(Number(filters.hero_id))) filters.hero_id = ''
  })
  const showFilters = $derived(!matchId && !(league && !teamId) && page !== 'queue' && page !== 'settings' && !isHidden('filters'))
  function monthsAgo(n: number) {
    const day = new Date()
    day.setMonth(day.getMonth() - n)
    return day.toLocaleDateString('en-CA') // YYYY-MM-DD in local time, what the API takes
  }

  /** The query's parameters that each filter of the panel sets, by the filter's Design id */
  const HIDES: Record<string, string> = {
    lobby_type: 'filters.lobby', game_mode: 'filters.mode', hero_id: 'filters.hero', league_id: 'filters.tournament',
    date_from: 'filters.time', date_to: 'filters.time',
  }
  // every view takes the same filters, so they travel as one query string
  const query = $derived.by(() => {
    const { span, ...dates } = time
    const sent = { ...filters, ...dates }
    if (span !== 'dates') [sent.date_from, sent.date_to] = [span === 'all' ? '' : monthsAgo(Number(span)), '']
    // a filter hidden in the Design settings counts as its default, so nothing narrows the page unseen
    const pairs: [string, string][] = Object.entries(sent).filter(([k, v]) => v !== '' && !(k in HIDES && isHidden(HIDES[k])))
    if (!league) {
      if (!isHidden('filters.role')) pairs.push(...ROLES[own.role][2].map((p): [string, string] => ['position', String(p)]))
      if (own.queue && !isHidden('filters.queue')) pairs.push(['party', String(own.queue === 2)])
      const size = isHidden('filters.matches') ? 100 : own.size
      if (size) pairs.push(['last', String(size)])
    }
    return new URLSearchParams(pairs).toString()
  })

  const loadAccounts = async () => (accounts = await get<Account[]>('accounts'))
  Promise.all([loadAccounts(), loadConstants(), loadSettings()]).then(
    ([found]) => {
      // the main profile from the settings, else the one picked last
      const known = (id: string | null | undefined) => found.some((a) => String(a.account_id) === id)
      const main = prefs.s?.main_account
      const remembered = localStorage.getItem('account_id')
      filters.account_id = known(main) ? main! : known(remembered) ? remembered! : String(found[0]?.account_id ?? '')
    },
    (e) => (error = e.message),
  )

  $effect(() => {
    if (filters.account_id) localStorage.setItem('account_id', filters.account_id)
  })

  // the Design settings' hidden parts: every element marked data-block with that id or one under it
  const hiding = document.head.appendChild(document.createElement('style'))
  $effect(() => {
    const ids = hiddenIds()
    hiding.textContent = ids.length ? `${ids.map((id) => `[data-block="${id}"], [data-block^="${id}."]`).join(', ')} { display: none !important; }` : ''
  })

  // #account/123 picks that tracked account and opens its profile: how other pages link to one
  function route() {
    if (location.hash === '#teams') history.replaceState(null, '', '#tournaments/teams') // where Teams was before
    const picked = /^account\/(\d+)$/.exec(location.hash.slice(1))?.[1]
    if (picked) {
      if (!accounts.some((a) => String(a.account_id) === picked)) loadAccounts() // added from a match page
      filters.account_id = picked
      localStorage.setItem('account_id', picked) // still the one picked once the accounts have loaded
      history.replaceState(null, '', '#profile')
    }
    hash = location.hash.slice(1)
  }
  route()

  let adding = $state(false) // the Add profile form is open
  let filtersOpen = $state(false) // on a narrow screen the filters fold behind a button, so the page shows first
  let selected = $state<{ games: number; parsed: number } | null>(null) // what the page below shows, for the panel's top line
  let belowTabs = $state(0) // px from the page's top to the end of its tabs: the panel starts level with what is under them
  function measureTabs(content: HTMLElement) {
    const measure = () => {
      const tabs = content.querySelector('[role=tablist]')
      belowTabs = tabs ? tabs.getBoundingClientRect().bottom + parseFloat(getComputedStyle(tabs).marginBottom) - content.getBoundingClientRect().top : 0
    }
    const watch = new ResizeObserver(measure) // the tabs appear once the page has its data, and the content grows then
    watch.observe(content)
    return { destroy: () => watch.disconnect() }
  }
  let newId = $state('')
  async function addProfile(event: SubmitEvent) {
    event.preventDefault()
    try {
      // sent as text: a Steam id is too long for a JavaScript number, the server reads it as one
      const { account_id } = await post<{ account_id: number }>('accounts', { account_id: newId.trim() })
      await loadAccounts()
      filters.account_id = String(account_id)
      ;[adding, newId, checked] = [false, '', 'Profile added. Its matches load with the next check.']
      location.hash = 'profile'
    } catch (e) {
      checked = `Could not add the profile: ${(e as Error).message}`
    }
  }
  const focus = (input: HTMLInputElement) => input.focus()

  const steamKey = $derived(prefs.s?.steam_key ?? true) // the server has a Steam Web API key; without one no new matches are fetched
  let newKey = $state('')
  let keyError = $state('')
  async function saveKey(event: SubmitEvent) {
    event.preventDefault()
    try {
      prefs.s = await post<Values>('settings/steam-key', { key: newKey })
    } catch (e) {
      keyError = (e as Error).message
    }
  }

  /** Asks the server again for what the page shows, without looking for new games */
  function reload() {
    version += 1
    loadAccounts()
    loadSettings()
  }

  let checking = $state(false)
  let checked = $state('') // what the last check found, or why it failed
  let version = $state(0) // goes up with every check; the page below is built anew, so it asks for its data again
  const some = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
  async function check() {
    checking = true
    checked = ''
    try {
      if (league) {
        const found = await post<{ league_games: number }>('teams/refresh')
        checked = some(found.league_games, 'new league game')
        if (teamId) {
          // then their players' games outside the league, for the role wheels, rather than at the poller's pace
          const asked = await post<{ players: number }>(`teams/${teamId}/players/refresh`)
          checked += `, the games of ${some(asked.players, 'player')} loaded`
        }
      } else {
        const found = await post<{ matches: number; waiting: number }>('refresh')
        checked = some(found.matches, 'new match', 'new matches')
        if (found.waiting) checked += `, ${some(found.waiting, 'match', 'matches')} still without a replay: the poller fetches them`
      }
      version += 1
    } catch (e) {
      checked = `Check failed: ${(e as Error).message}`
    }
    checking = false
  }
</script>

<svelte:window onhashchange={route} />

<main>
  <header class="top">
    <h1><a class="brand" href="#"><img src="/logo.png" alt="DotAnalyst" width="209" height="32" /></a></h1>
    <nav aria-label="Pages">
      {#each NAV as id}
        <a href="#{id}" data-block={id} aria-current={(teamId || leagueId ? id === 'tournaments' : !matchId && page === id) ? 'page' : undefined}>{PAGES[id]}</a>
      {/each}
    </nav>
    <div class="side">
      <Progress current={!matchId && page === 'queue'} />
      <button class="action reload" onclick={reload} title="Reload what the page shows" aria-label="Reload what the page shows">↻</button>
      {#if adding}
        <form class="add" onsubmit={addProfile}>
          <input bind:value={newId} use:focus required pattern="\s*\d+\s*" inputmode="numeric" aria-label="Friend id or Steam id" placeholder="Friend id or Steam id" />
          <button class="action">Add</button>
          <button class="action" type="button" onclick={() => (adding = false)}>Cancel</button>
        </form>
      {:else}
        <button class="action" onclick={() => (adding = true)}>Add profile</button>
      {/if}
      <span class="muted" role="status">{checked}</span>
      <button class="action" onclick={check} disabled={checking}>
        {checking ? 'Checking…' : teamId ? 'Refresh' : league ? 'Check for new league games' : 'Check for new games'}
      </button>
      <a class="action gear" href="#settings" aria-current={page === 'settings' ? 'page' : undefined} title="Settings" aria-label="Settings">⚙</a>
    </div>
  </header>
  {#if !steamKey}
    <form class="add" onsubmit={saveKey}>
      <span>No new matches are fetched without a Steam Web API key. Get one at <a href="https://steamcommunity.com/dev/apikey" target="_blank" rel="noreferrer">steamcommunity.com/dev/apikey</a>:</span>
      <input bind:value={newKey} required aria-label="Steam Web API key" placeholder="Steam Web API key" size="34" />
      <button class="action">Save</button>
      <span class="error" role="alert">{keyError}</span>
    </form>
  {/if}

  <div class="layout" class:paneled={showFilters} style:--below-tabs="{belowTabs}px">
  {#if showFilters}
    <!-- every tab below takes all of these. A team page takes only the time and the season: its games are league games -->
    <aside class="panel" class:folded={!filtersOpen} aria-label="Filters">
      <button class="action fold" aria-expanded={filtersOpen} onclick={() => (filtersOpen = !filtersOpen)}>Filters {filtersOpen ? '▴' : '▾'}</button>
      {#if selected}
        <p class="selected" role="status">
          <b>{selected.games}</b> {selected.games === 1 ? 'match' : 'matches'} selected
          <span class="muted">{selected.parsed} of them with a parsed replay</span>
        </p>
      {/if}
      {#if !league}
        <section data-block="filters.matches">
          <h3>Matches</h3>
          <div class="choice" role="group" aria-label="How many of the newest matches">
            {#each SIZES as n}<button aria-pressed={own.size === n} onclick={() => (own.size = n)}>{n || 'All'}</button>{/each}
          </div>
        </section>
        <section data-block="filters.role">
          <h3>Role</h3>
          <div class="choice roles" role="group" aria-label="Role">
            {#each ROLES as [short, long, positions], i}
              <button aria-pressed={own.role === i} title={long} aria-label={long} onclick={() => (own.role = i)}>
                {#if positions.length === 1}<img src="/roles/{MARKS.get(positions[0])}.png" alt="" width="20" height="20" />{:else}{short}{/if}
              </button>
            {/each}
          </div>
        </section>
        <section data-block="filters.queue">
          <h3>Queue</h3>
          <div class="choice" role="group" aria-label="Solo or party">
            {#each QUEUES as name, i}<button aria-pressed={own.queue === i} onclick={() => (own.queue = i)}>{name}</button>{/each}
          </div>
        </section>
        <section data-block="filters.lobby">
          <h3>Lobby</h3>
          <div class="choice" role="group" aria-label="Lobby">
            {#each [['', 'All'], ...Object.entries(LOBBY_TYPES)] as [id, name]}
              <button aria-pressed={filters.lobby_type === id} onclick={() => (filters.lobby_type = id)}>{name}</button>
            {/each}
          </div>
        </section>
        <section data-block="filters.mode">
          <h3><label for="mode">Mode</label></h3>
          <select id="mode" bind:value={filters.game_mode}>
            <option value="">All modes</option>
            {#each Object.entries(GAME_MODES).filter(([id]) => id !== '1') as [id, name]}
              <option value={id}>{name}</option>
            {/each}
          </select>
        </section>
        <section data-block="filters.hero">
          <h3>Hero</h3>
          <div class="choice heroes" role="group" aria-label="Hero">
            <button class="all" aria-pressed={filters.hero_id === ''} onclick={() => (filters.hero_id = '')}>All heroes</button>
            {#each heroes as id}
              <button aria-pressed={filters.hero_id === String(id)} onclick={() => (filters.hero_id = String(id))}>
                <img src={heroIcon(id)} alt={heroName(id)} title={heroName(id)} width="24" height="24" />
              </button>
            {/each}
          </div>
        </section>
      {/if}
      <section data-block="filters.time">
        <h3>Time</h3>
        <div class="choice spans" role="group" aria-label="Time">
          {#each SPANS as [id, name]}
            <button aria-pressed={time.span === id} onclick={() => (time.span = id)}>{name}</button>
          {/each}
        </div>
        {#if time.span === 'dates'}
          <label class="day">From <input type="date" bind:value={time.date_from} /></label>
          <label class="day">To <input type="date" bind:value={time.date_to} /></label>
        {/if}
      </section>
      {#if league}<!-- a team's season; the profile and the comparison take every game -->
        <section data-block="filters.tournament">
          <h3><label for="tournament">Tournament</label></h3>
          <select id="tournament" bind:value={time.league_id}>
            <option value="">All games</option>
            {#each Object.entries(constants.leagues).reverse() as [id, name]}<option value={id}>{name}</option>{/each}
          </select>
        </section>
      {/if}
    </aside>
  {/if}

  <div class="content" use:measureTabs>
  {#key version}
  {#if error}
    <p class="error" role="alert">Could not reach the API: {error}</p>
  {:else if matchId}
    <Match id={matchId} />
  {:else if leagueId}
    <League id={leagueId} tab={leagueRoute?.[2] ?? ''} />
  {:else if teamId}
    <Team id={teamId} {query} onshown={(s) => (selected = s)} />
  {:else if page === 'tournaments'}
    <Tournaments tab={tournamentsTab} />
  {:else if page === 'queue'}
    <Queue />
  {:else if page === 'settings'}
    <Settings tab={settingsTab} {accounts} onaccounts={loadAccounts} />
  {:else if !filters.account_id}
    <p class="muted">No tracked accounts yet. Add one with Add profile above, by its friend id or Steam id.</p>
  {:else if page === 'profile'}
    <Profile
      {query}
      tab={profileTab}
      ontracked={loadAccounts}
      onshown={(s) => (selected = s)}
      positions={ROLES[own.role][2]}
      onpositions={(p) => (own.role = Math.max(0, ROLES.findIndex(([, , r]) => r.join() === p.join())))}
      {accounts}
      onaccount={(id) => (filters.account_id = id)}
      account={accounts.find((a) => String(a.account_id) === filters.account_id)} />
  {:else}
    <Compare {query} {accounts} />
  {/if}
  {/key}
  </div>
  </div>
</main>
