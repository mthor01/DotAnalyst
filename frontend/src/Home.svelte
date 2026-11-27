<script lang="ts">
  import { get, post } from './lib/api'
  import { loadConstants } from './lib/constants.svelte'
  import LeagueList from './lib/LeagueList.svelte'
  import MatchBoard from './lib/MatchBoard.svelte'
  import TournamentLine from './lib/TournamentLine.svelte'
  import type { CatalogRow, HomeAnswer } from './lib/leagues'

  // Home: Explore of your tournaments (explore.home), and the search to find and subscribe to more
  let found = $state<HomeAnswer | null>(null)
  let error = $state('')
  const load = () => get<HomeAnswer>('home').then((a) => (found = a), (e) => (error = e.message))
  load()
  const league = (id: number | string) => found?.leagues[String(id)]

  // ---- Search: asked of the server 300 ms after the last key, a page of 50 at a time; anything typed or picked
  // shows the results in place of the overview
  const PAGE = 50
  let search = $state({ text: '', tier: '', state: '', sort: 'last' })
  const asking = $derived(!!search.text.trim() || !!search.tier || !!search.state || search.sort !== 'last')
  let results = $state<CatalogRow[]>([])
  let more = $state(false) // a full page came: there may be more
  let searching = $state(false)
  const params = (offset: number) => new URLSearchParams({ ...search, offset: String(offset) }).toString()
  async function find(offset: number) {
    searching = true
    try {
      const page = await get<CatalogRow[]>('catalog', params(offset))
      results = offset ? [...results, ...page] : page
      more = page.length === PAGE
    } catch (e) {
      error = (e as Error).message
    }
    searching = false
  }
  $effect(() => {
    if (!asking) return
    params(0) // read every field, so a change of any runs it again
    const timer = setTimeout(() => find(0), 300)
    return () => clearTimeout(timer)
  })
  // back from a search: what was subscribed there shows
  let wasAsking = false
  $effect(() => {
    if (wasAsking && !asking) load()
    wasAsking = asking
  })

  // ---- Add by league id: for a league no list has
  let leagueId = $state('')
  let adding = $state(false)
  let added = $state('') // what the last add did, or why it failed
  async function add(event: SubmitEvent) {
    event.preventDefault()
    adding = true
    try {
      // sent as text: the server reads it as a number, without JavaScript rounding a long id
      const done = await post<{ name: string }>('leagues', { league_id: leagueId })
      added = `${done.name} is subscribed. Its games load with the next check.`
      leagueId = ''
      load()
      await loadConstants() // for the header's Tournament filter
    } catch (e) {
      added = `Could not add it: ${(e as Error).message}`
    }
    adding = false
  }
</script>

{#snippet side()}
  <section data-block="tournaments.home.mine">
    <h2>Your tournaments</h2>
    <ul class="card lines">{#each found?.mine ?? [] as id (id)}{@const l = league(id)}{#if l}<TournamentLine league={l} />{/if}{/each}</ul>
  </section>
{/snippet}

<form class="filters" onsubmit={(e) => e.preventDefault()}>
  <input class="text" bind:value={search.text} type="search" placeholder="Find a tournament" aria-label="Tournament name" />
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

{#if error}<p class="error" role="alert">{error}</p>{/if}

{#if asking}
  <LeagueList rows={results} empty={searching ? 'Searching…' : 'No league with this name, tier and status.'} />
  {#if more}<p><button class="action" disabled={searching} onclick={() => find(results.length)}>Show more</button></p>{/if}
{:else if !found}
  {#if !error}<p class="muted">Loading…</p>{/if}
{:else if !found.mine.length}
  <p class="muted">You follow no tournament yet: find one above, or look around <a href="#tournaments/explore">Explore</a>.</p>
{:else}
  <MatchBoard
    live={found.live}
    upcoming={found.upcoming}
    results={found.results}
    {league}
    block="tournaments.home"
    upcomingTitle="Coming up in the next 7 days"
    aside={side}
    empty={{
      live: 'None of your tournaments is playing right now. Steam is asked every 5 minutes.',
      upcoming: 'No match of your tournaments on Liquipedia in the next 7 days. Only tournaments with a Liquipedia page list theirs.',
      results: 'None of your tournaments played in the last 7 days.',
    }}
  />
{/if}

<form class="filters byid" onsubmit={add}>
  <label>
    Not listed? Subscribe by league id
    <input class="id" bind:value={leagueId} required pattern="\d+" inputmode="numeric" placeholder="league id" />
  </label>
  <button class="action" disabled={adding}>{adding ? 'Adding…' : 'Subscribe'}</button>
  <span class="muted" role="status">{added}</span>
</form>

<p class="muted credit">
  Upcoming matches, tiers, prize pools, dates and places from
  <a href="https://liquipedia.net/dota2/" target="_blank" rel="noreferrer">Liquipedia</a>, CC BY-SA 3.0.
</p>

<style>
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
    margin-top: 26px;
  }
  .credit {
    margin-top: 30px;
    font-size: 13px;
  }
  h2 {
    margin: 26px 0 10px;
    font-size: 17px;
  }
  .lines {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow: hidden;
  }
</style>
