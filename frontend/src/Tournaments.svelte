<script lang="ts">
  import { get, post, type TournamentRow } from './lib/api'
  import { loadConstants } from './lib/constants.svelte'
  import LeagueList from './lib/LeagueList.svelte'
  import { day, subscribe, type CatalogRow } from './lib/leagues'
  import { shownTab } from './lib/settings.svelte'
  import Teams from './Teams.svelte'

  let { tab }: { tab: string } = $props()
  // the tabs by their Design id; #tournaments is Search, the home: your tournaments, and every other one by name.
  // #tournaments/subscribed and #tournaments/search, from before, are Search too
  const TABS = { search: 'Search', explore: 'Explore', teams: 'Teams' }
  type Tab = keyof typeof TABS
  const HASH: Record<Tab, string> = { search: 'tournaments', explore: 'tournaments/explore', teams: 'tournaments/teams' }
  const wanted = $derived<Tab>(tab in TABS ? (tab as Tab) : 'search')
  const shown = $derived(shownTab('tournaments', Object.keys(TABS) as Tab[], wanted)) // a hidden tab gives way
  let error = $state('')

  // ---- Explore
  let explore = $state<{ live: CatalogRow[]; big: CatalogRow[] } | null>(null)
  $effect(() => {
    if (shown === 'explore') get<typeof explore>('explore').then((found) => (explore = found), (e) => (error = e.message))
  })

  // ---- Search: asked of the server 300 ms after the last key, a page of 50 at a time; with nothing typed or picked,
  // your tournaments instead
  const PAGE = 50
  let search = $state({ text: '', tier: '', state: '', sort: 'last' })
  const asking = $derived(!!search.text.trim() || !!search.tier || !!search.state || search.sort !== 'last')
  let found = $state<CatalogRow[]>([])
  let more = $state(false) // a full page came: there may be more
  let searching = $state(false)
  const params = (offset: number) => new URLSearchParams({ ...search, offset: String(offset) }).toString()
  async function find(offset: number) {
    searching = true
    try {
      const page = await get<CatalogRow[]>('catalog', params(offset))
      found = offset ? [...found, ...page] : page
      more = page.length === PAGE
    } catch (e) {
      error = (e as Error).message
    }
    searching = false
  }
  $effect(() => {
    if (shown !== 'search' || !asking) return
    params(0) // read every field, so a change of any runs it again
    const timer = setTimeout(() => find(0), 300)
    return () => clearTimeout(timer)
  })

  // ---- Your tournaments, on Search with nothing asked
  let rows = $state<TournamentRow[] | null>(null)
  const load = () => get<TournamentRow[]>('leagues').then((found) => (rows = found), (e) => (error = e.message))
  $effect(() => {
    if (shown === 'search' && !asking) load()
  })
  async function unsubscribe(r: TournamentRow) {
    if (!confirm(`Unsubscribe from ${r.name}? Its stored games stay; no new ones are fetched.`)) return
    await subscribe({ league_id: r.league_id, subscribed: true }, false).then(load, (e) => (error = e.message))
  }

  // ---- Add by league id: for a league no list has
  let leagueId = $state('')
  let adding = $state(false)
  let added = $state('') // what the last add did, or why it failed
  async function add(event: SubmitEvent) {
    event.preventDefault()
    adding = true
    try {
      // sent as text: the server reads it as a number, without JavaScript rounding a long id
      const found = await post<{ name: string }>('leagues', { league_id: leagueId })
      added = `${found.name} is subscribed. Its games load with the next check.`
      leagueId = ''
      load() // it joins Your tournaments
      await loadConstants() // for the header's Tournament filter
    } catch (e) {
      added = `Could not add it: ${(e as Error).message}`
    }
    adding = false
  }
</script>

<div class="choice tabs" role="group" aria-label="Part of the tournaments page">
  {#each Object.entries(TABS) as [id, title]}
    <button data-block="tournaments.{id}" aria-pressed={shown === id} onclick={() => ((error = ''), (location.hash = HASH[id as Tab]))}>{title}</button>
  {/each}
</div>

{#if error}<p class="error" role="alert">{error}</p>{/if}

{#if shown === 'teams'}
  <Teams />
{:else if shown === 'explore'}
  {#if !explore}
    <p class="muted">Loading…</p>
  {:else}
    <h2>Live now</h2>
    <p class="muted">Leagues with a game on Steam right now, amateur ones too. A league that plays rarely shows up here only while it plays.</p>
    <LeagueList rows={explore.live} empty="No league game is live right now, or Steam was not asked yet: the site asks every 5 minutes." />
    <h2>Biggest of the last 30 days</h2>
    <p class="muted">By Liquipedia tier, then prize pool, then games played. Amateur leagues count once they were seen live or opened.</p>
    <LeagueList rows={explore.big} empty="No league played in the last 30 days, or OpenDota's list was not read yet: it is read once a day." />
  {/if}
{:else if shown === 'search'}
  <form class="filters" onsubmit={(e) => e.preventDefault()}>
    <input class="text" bind:value={search.text} type="search" placeholder="Tournament name" aria-label="Tournament name" />
    <label>Tier
      <select bind:value={search.tier}>
        <option value="">All</option><option value="premium">Premium</option><option value="professional">Pro</option><option value="amateur">Amateur</option>
      </select>
    </label>
    <label>Status
      <select bind:value={search.state}>
        <option value="">Any</option><option value="live">Live</option><option value="active">Active</option><option value="finished">Finished</option><option value="unknown">Unknown</option>
      </select>
    </label>
    <label>Sort by
      <select bind:value={search.sort}>
        <option value="last">Last game</option><option value="games">Games</option><option value="prize">Prize pool</option><option value="newest">Newest</option><option value="name">Name</option>
      </select>
    </label>
  </form>
  {#if asking}
    <LeagueList rows={found} empty={searching ? 'Searching…' : 'No league with this name, tier and status.'} />
    {#if more}<p><button class="action" disabled={searching} onclick={() => find(found.length)}>Show more</button></p>{/if}
  {:else}
    <h2>Your tournaments</h2>
    <div class="card">
      <table>
        <thead>
          <tr><th>Tournament</th><th class="num">Games</th><th class="num">Teams</th><th>First game</th><th>Last game</th><th></th></tr>
        </thead>
        <tbody>
          {#each rows ?? [] as r (r.league_id)}
            <tr>
              <td><a href="#league/{r.league_id}">{r.name}</a> <span class="muted">{r.league_id}</span></td>
              <td class="num">{r.games}</td>
              <td class="num">{r.teams}</td>
              <td class="muted">{day(r.first_game)}</td>
              <td class="muted">{day(r.last_game)}</td>
              <td class="num"><button class="action" onclick={() => unsubscribe(r)}>Unsubscribe</button></td>
            </tr>
          {:else}
            <tr><td colspan="6" class="muted">
              {rows ? 'You follow no tournament yet: type a name above, or find one under' : 'Loading…'}
              {#if rows}<a href="#tournaments/explore">Explore</a>.{/if}
            </td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
  <form class="filters byid" onsubmit={add}>
    <label>
      Not listed? Subscribe by league id
      <input class="id" bind:value={leagueId} required pattern="\d+" inputmode="numeric" placeholder="league id" />
    </label>
    <button class="action" disabled={adding}>{adding ? 'Adding…' : 'Subscribe'}</button>
    <span class="muted" role="status">{added}</span>
  </form>
{/if}

<style>
  .tabs {
    margin: 4px 0 14px;
  }
  .filters {
    flex-wrap: wrap;
    margin: 0 0 14px;
  }
  .text {
    width: 18em;
  }
  .id {
    width: 9em;
  }
  .byid {
    margin-top: 22px;
  }
  h2 {
    margin: 22px 0 4px;
  }
  h2:first-of-type {
    margin-top: 0;
  }
</style>
