<script lang="ts">
  import { GAME_MODES, LOBBY_TYPES, get, type Account } from './lib/api'
  import { loadConstants } from './lib/constants.svelte'
  import Heroes from './Heroes.svelte'
  import Matches from './Matches.svelte'
  import Teammates from './Teammates.svelte'

  const PAGES = { matches: 'Matches', heroes: 'Heroes', teammates: 'Teammates & matchups' }
  type Page = keyof typeof PAGES
  const pageFromHash = (): Page => {
    const hash = location.hash.slice(1)
    return hash in PAGES ? (hash as Page) : 'matches'
  }

  let page = $state(pageFromHash())
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

<svelte:window onhashchange={() => (page = pageFromHash())} />

<main>
  <header>
    <h1>DotAnalyst</h1>
    <nav aria-label="Pages">
      {#each Object.entries(PAGES) as [id, title]}
        <a href="#{id}" aria-current={page === id ? 'page' : undefined}>{title}</a>
      {/each}
    </nav>
  </header>

  <div class="filters">
    <label>
      Account
      <select bind:value={filters.account_id}>
        {#each accounts as a}
          <option value={String(a.account_id)}>{a.label ?? a.account_id}</option>
        {/each}
      </select>
    </label>
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
  {:else if !filters.account_id}
    <p class="muted">No tracked accounts yet. Add one with <code>dotanalyst add-account</code>.</p>
  {:else if page === 'matches'}
    <Matches {query} />
  {:else if page === 'heroes'}
    <Heroes {query} />
  {:else}
    <Teammates {query} />
  {/if}
</main>
