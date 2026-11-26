<script lang="ts">
  import Explore from './Explore.svelte'
  import Home from './Home.svelte'
  import { shownTab } from './lib/settings.svelte'
  import Teams from './Teams.svelte'

  let { tab }: { tab: string } = $props()
  // the tabs by their Design id; #tournaments is Home, every other one by name. #tournaments/search and
  // #tournaments/subscribed, from before, land on Home too
  const TABS = { home: 'Home', explore: 'Explore', teams: 'Teams' }
  type Tab = keyof typeof TABS
  const HASH: Record<Tab, string> = { home: 'tournaments', explore: 'tournaments/explore', teams: 'tournaments/teams' }
  const wanted = $derived<Tab>(tab in TABS ? (tab as Tab) : 'home')
  const shown = $derived(shownTab('tournaments', Object.keys(TABS) as Tab[], wanted)) // a hidden tab gives way
</script>

<div class="choice tabs" role="group" aria-label="Part of the tournaments page">
  {#each Object.entries(TABS) as [id, title]}
    <button data-block="tournaments.{id}" aria-pressed={shown === id} onclick={() => (location.hash = HASH[id as Tab])}>{title}</button>
  {/each}
</div>

{#if shown === 'teams'}
  <Teams />
{:else if shown === 'explore'}
  <Explore />
{:else if shown === 'home'}
  <Home />
{/if}

<style>
  .tabs {
    margin: 4px 0 14px;
  }
</style>
