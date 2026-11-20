<script lang="ts">
  import { GAME_MODES, LOBBY_TYPES, get, post, type Account } from './lib/api'
  import { constants, loadConstants } from './lib/constants.svelte'
  import Match from './Match.svelte'
  import Compare from './Compare.svelte'
  import Profile from './Profile.svelte'
  import Progress from './lib/Progress.svelte'
  import Queue from './Queue.svelte'
  import Team from './Team.svelte'
  import Tournaments from './Tournaments.svelte'

  const PAGES = { profile: 'Profile', compare: 'Player comparison', tournaments: 'Tournaments', queue: 'Queue' }
  const ALL_ACCOUNTS: Page[] = ['compare'] // these pages show every tracked account at once
  type Page = keyof typeof PAGES
  let hash = $state(location.hash.slice(1))
  const page = $derived<Page>(hash.split('/')[0] in PAGES ? (hash.split('/')[0] as Page) : 'profile')
  const profileTab = $derived(/^profile\/(\w+)$/.exec(hash)?.[1] ?? '') // #profile/matches is a tab of the profile
  const matchId = $derived(/^match\/(\d+)$/.exec(hash)?.[1]) // #match/123 is one match, outside the pages above
  const teamId = $derived(/^team\/(\d+)$/.exec(hash)?.[1]) // #team/123 is one league team, under Tournaments
  const tournamentsTab = $derived(/^tournaments\/(\w+)$/.exec(hash)?.[1] ?? '') // #tournaments/teams is its Teams tab
  // the league pages are about other people's games: no account and none of the filters apply
  const league = $derived(!!teamId || (!matchId && page === 'tournaments'))
  let accounts = $state<Account[]>([])
  let error = $state('')
  let filters = $state({ account_id: '', lobby_type: '', game_mode: '' })
  // a number is that many months back from today; only "dates" uses the From and To days
  const SPANS = { '1': 'Last month', '3': 'Last 3 months', '6': 'Last 6 months', '12': 'Last year', all: 'All time', dates: 'Dates…' }
  // season and time: the team pages keep their own, so a team's season does not narrow the profile
  const times = $state({
    player: { league_id: '', span: 'all', date_from: '', date_to: '' },
    team: { league_id: '', span: 'all', date_from: '', date_to: '' },
  })
  const time = $derived(league ? times.team : times.player)
  function monthsAgo(n: number) {
    const day = new Date()
    day.setMonth(day.getMonth() - n)
    return day.toLocaleDateString('en-CA') // YYYY-MM-DD in local time, what the API takes
  }

  // every view takes the same filters, so they travel as one query string
  const query = $derived.by(() => {
    const { span, ...dates } = time
    const sent = { ...filters, ...dates }
    if (span !== 'dates') [sent.date_from, sent.date_to] = [span === 'all' ? '' : monthsAgo(Number(span)), '']
    return new URLSearchParams(Object.entries(sent).filter(([, v]) => v !== '')).toString()
  })

  const loadAccounts = async () => (accounts = await get<Account[]>('accounts'))
  Promise.all([loadAccounts(), loadConstants()]).then(
    ([found]) => {
      const remembered = localStorage.getItem('account_id')
      const known = found.some((a) => String(a.account_id) === remembered)
      filters.account_id = known ? remembered! : String(found[0]?.account_id ?? '')
    },
    (e) => (error = e.message),
  )

  $effect(() => {
    if (filters.account_id) localStorage.setItem('account_id', filters.account_id)
  })

  // #account/123 picks that tracked account and opens its profile: how other pages link to one
  function route() {
    if (location.hash === '#teams') history.replaceState(null, '', '#tournaments/teams') // where Teams was before
    const picked = /^account\/(\d+)$/.exec(location.hash.slice(1))?.[1]
    if (picked) {
      filters.account_id = picked
      localStorage.setItem('account_id', picked) // still the one picked once the accounts have loaded
      history.replaceState(null, '', '#profile')
    }
    hash = location.hash.slice(1)
  }
  route()

  let adding = $state(false) // the Add profile form is open
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
    <h1><a class="brand" href="#{Object.keys(PAGES)[0]}"><img src="/logo.png" alt="DotAnalyst" width="209" height="32" /></a></h1>
    <nav aria-label="Pages">
      {#each Object.entries(PAGES) as [id, title]}
        <a href="#{id}" aria-current={(teamId ? id === 'tournaments' : !matchId && page === id) ? 'page' : undefined}>{title}</a>
      {/each}
    </nav>
    <div class="side">
      <label hidden={!!matchId || league || ALL_ACCOUNTS.includes(page) || page === 'queue'}>
        Account
        <select bind:value={filters.account_id}>
          {#each accounts as a}
            <option value={String(a.account_id)}>{a.label ?? a.account_id}</option>
          {/each}
        </select>
      </label>
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
    </div>
  </header>
  <Progress />

  <!-- a team page takes the time and the season; lobby and mode are the same in every league game -->
  <div class="filters" hidden={!!matchId || (league && !teamId) || page === 'queue'}>
    <label hidden={league}>
      Lobby
      <select bind:value={filters.lobby_type}>
        <option value="">All</option>
        {#each Object.entries(LOBBY_TYPES) as [id, name]}<option value={id}>{name}</option>{/each}
      </select>
    </label>
    <label hidden={league}>
      Mode
      <select bind:value={filters.game_mode}>
        <option value="">All</option>
        {#each Object.entries(GAME_MODES).filter(([id]) => id !== '1') as [id, name]}
          <option value={id}>{name}</option>
        {/each}
      </select>
    </label>
    <label>
      Tournament
      <select bind:value={time.league_id}>
        <option value="">All games</option>
        {#each Object.entries(constants.leagues).reverse() as [id, name]}<option value={id}>{name}</option>{/each}
      </select>
    </label>
    <label>
      Time
      <select bind:value={time.span}>
        {#each Object.entries(SPANS) as [id, name]}<option value={id}>{name}</option>{/each}
      </select>
    </label>
    {#if time.span === 'dates'}
      <label>From <input type="date" bind:value={time.date_from} /></label>
      <label>To <input type="date" bind:value={time.date_to} /></label>
    {/if}
  </div>

  {#key version}
  {#if error}
    <p class="error" role="alert">Could not reach the API: {error}</p>
  {:else if matchId}
    <Match id={matchId} />
  {:else if teamId}
    <Team id={teamId} {query} />
  {:else if page === 'tournaments'}
    <Tournaments tab={tournamentsTab} />
  {:else if page === 'queue'}
    <Queue />
  {:else if !filters.account_id}
    <p class="muted">No tracked accounts yet. Add one with Add profile above, by its friend id or Steam id.</p>
  {:else if page === 'profile'}
    <Profile {query} tab={profileTab} ontracked={loadAccounts} account={accounts.find((a) => String(a.account_id) === filters.account_id)} />
  {:else}
    <Compare {query} {accounts} />
  {/if}
  {/key}
</main>
