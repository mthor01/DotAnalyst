<script lang="ts">
  import { GAME_MODES, LOBBY_TYPES, get, type Account } from './lib/api'
  import { loadConstants } from './lib/constants.svelte'
  import Heroes from './Heroes.svelte'
  import Match from './Match.svelte'
  import Matches from './Matches.svelte'
  import Group from './Group.svelte'
  import Profile from './Profile.svelte'
  import Teammates from './Teammates.svelte'
  import Trends from './Trends.svelte'

  const PAGES = { profile: 'Profile', matches: 'Matches', heroes: 'Heroes', teammates: 'Teammates & matchups', trends: 'Trends', group: 'Group' }
  const ALL_ACCOUNTS: Page[] = ['trends', 'group'] // these pages show every tracked account at once
  type Page = keyof typeof PAGES
  let hash = $state(location.hash.slice(1))
  const page = $derived<Page>(hash in PAGES ? (hash as Page) : 'profile')
  const matchId = $derived(/^match\/(\d+)$/.exec(hash)?.[1]) // #match/123 is one match, outside the pages above
  let accounts = $state<Account[]>([])
  let error = $state('')
  let filters = $state({ account_id: '', lobby_type: '', game_mode: '', date_from: '', date_to: '' })

  // every view takes the same filters, so they travel as one query string
  const query = $derived(new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== '')).toString())

  Promise.all([get<Account[]>('accounts'), loadConstants()]).then(
    ([found]) => {
      accounts = found
      const remembered = localStorage.getItem('account_id')
      const known = found.some((a) => String(a.account_id) === remembered)
      filters.account_id = known ? remembered! : String(found[0]?.account_id ?? '')
    },
    (e) => (error = e.message),
  )

  $effect(() => {
    if (filters.account_id) localStorage.setItem('account_id', filters.account_id)
  })
</script>

<svelte:window onhashchange={() => (hash = location.hash.slice(1))} />

<main>
  <header class="top">
    <h1><a class="brand" href="#{Object.keys(PAGES)[0]}">DotAnalyst</a></h1>
    <nav aria-label="Pages">
      {#each Object.entries(PAGES) as [id, title]}
        <a href="#{id}" aria-current={!matchId && page === id ? 'page' : undefined}>{title}</a>
      {/each}
    </nav>
    <label class="who" hidden={!!matchId || ALL_ACCOUNTS.includes(page)}>
      Account
      <select bind:value={filters.account_id}>
        {#each accounts as a}
          <option value={String(a.account_id)}>{a.label ?? a.account_id}</option>
        {/each}
      </select>
    </label>
  </header>

  <div class="filters" hidden={!!matchId}>
    <label>
      Lobby
      <select bind:value={filters.lobby_type}>
        <option value="">All</option>
        {#each Object.entries(LOBBY_TYPES) as [id, name]}<option value={id}>{name}</option>{/each}
      </select>
    </label>
    <label>
      Mode
      <select bind:value={filters.game_mode}>
        <option value="">All</option>
        {#each Object.entries(GAME_MODES).filter(([id]) => id !== '1') as [id, name]}
          <option value={id}>{name}</option>
        {/each}
      </select>
    </label>
    <label>From <input type="date" bind:value={filters.date_from} /></label>
    <label>To <input type="date" bind:value={filters.date_to} /></label>
  </div>

  {#if error}
    <p class="error" role="alert">Could not reach the API: {error}</p>
  {:else if matchId}
    <Match id={matchId} />
  {:else if !filters.account_id}
    <p class="muted">No tracked accounts yet. Add one with <code>dotanalyst add-account</code>.</p>
  {:else if page === 'profile'}
    <Profile {query} account={accounts.find((a) => String(a.account_id) === filters.account_id)} />
  {:else if page === 'matches'}
    <Matches {query} />
  {:else if page === 'heroes'}
    <Heroes {query} />
  {:else if page === 'trends'}
    <Trends {query} {accounts} />
  {:else if page === 'group'}
    <Group {query} {accounts} />
  {:else}
    <Teammates {query} />
  {/if}
</main>
