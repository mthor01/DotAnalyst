<script lang="ts">
  import { STATUS, TIER_COLOR, liquipedia, money, subscribe, tierGroup, type ExploreLeague } from './leagues'

  // one tournament as a row of Explore's and Home's side column: its tier as the colour of the left edge, as on the
  // calendar. One only Liquipedia's list knows (no league id yet) links to Liquipedia and cannot be subscribed to
  let { league, winner = undefined, toggle = true }: {
    league: ExploreLeague; winner?: { name: string; logo: string | null } | null; toggle?: boolean
  } = $props()
  let failed = $state('')
  const DAY = 86400000
  const date = (d: string | null) => (d ? Date.parse(`${d}T12:00:00Z`) : null)
  const start = $derived(date(league.start_date) ?? (league.first_game ? league.first_game * 1000 : null))
  const end = $derived(date(league.end_date) ?? (league.last ? league.last * 1000 : null))
  const short = (t: number, year = false) =>
    new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', ...(year && { year: 'numeric' }), timeZone: 'UTC' })
  const when = $derived(start === null ? '' : end === null || short(start) === short(end) ? short(start) : `${short(start)} – ${short(end)}`)
  const upcoming = $derived(winner === undefined && start !== null && start > Date.now())
  const days = $derived(start === null ? 0 : Math.ceil((start - Date.now()) / DAY))
  const status = $derived(
    winner !== undefined ? '' : upcoming ? (days <= 1 ? 'Starts tomorrow' : `In ${days} days`) : league.status === 'live' ? 'Live' : STATUS[league.status],
  )
  const href = $derived(league.league_id !== null ? `#league/${league.league_id}` : league.lp_page ? liquipedia(league.lp_page) : undefined)
  async function flip() {
    try {
      await subscribe(league as ExploreLeague & { league_id: number }, !league.subscribed)
      failed = ''
    } catch (e) {
      failed = (e as Error).message
    }
  }
</script>

<li style:--tier={TIER_COLOR[tierGroup(league.lp_tier)]}>
  <div class="headline">
    <a class="name" {href} target={league.league_id === null ? '_blank' : undefined} rel={league.league_id === null ? 'noopener' : undefined}
      title={league.league_id === null ? `${league.name} on Liquipedia` : league.name}>{league.name}</a>
    <span class="when">{when}</span>
  </div>
  <div class="facts">
    {#if league.lp_tier}<span>Tier {league.lp_tier}</span>{/if}
    {#if league.prize_usd}<span>{money(league.prize_usd)}</span>{/if}
    {#if league.location}<span class="place">{league.location}</span>{/if}
    {#if status}<span class="status" class:live={league.status === 'live' && !upcoming}>{status}</span>{/if}
  </div>
  {#if winner !== undefined}
    <div class="winner">
      {#if winner}
        {#if winner.logo}<img src={winner.logo} alt="" width="18" height="18" />{/if}
        <span>Won by <strong>{winner.name}</strong></span>
      {:else}
        <span class="muted">Winner not known</span>
      {/if}
    </div>
  {/if}
  {#if toggle && league.league_id !== null}
    <button class="follow" aria-pressed={league.subscribed} onclick={flip}>{league.subscribed ? 'Subscribed ✓' : 'Subscribe'}</button>
    {#if failed}<span class="error" role="alert">{failed}</span>{/if}
  {/if}
</li>

<style>
  li {
    display: grid;
    gap: 3px;
    padding: 8px 12px 9px 12px;
    border-left: 3px solid var(--tier);
    position: relative;
  }
  li + li {
    border-top: 1px solid var(--border);
  }
  .headline {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    min-width: 0;
  }
  .name {
    font-weight: 600;
    color: var(--text);
    text-decoration: none;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .name:hover {
    text-decoration: underline;
  }
  .when {
    flex: none;
    font-size: 12px;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  .facts {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 12px;
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .place {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    max-width: 16em;
  }
  .status {
    margin-left: auto;
    color: var(--text-2);
  }
  .status.live {
    color: var(--good);
    font-weight: 600;
  }
  .winner {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 13px;
  }
  .winner img {
    object-fit: contain;
  }
  .follow {
    justify-self: start;
    margin-top: 3px;
    padding: 0;
    border: 0;
    background: none;
    color: var(--series-1);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
  }
  .follow[aria-pressed='true'] {
    color: var(--muted);
  }
  .follow:hover {
    text-decoration: underline;
  }
</style>
