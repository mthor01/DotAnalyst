<script lang="ts">
  import { STATUS, TIER_COLOR, dates, money, subscribe, tierGroup, type ExploreLeague } from './leagues'

  // one tournament on Explore: its tier as the colour of the left edge, as on the calendar
  let { league, winner = undefined }: { league: ExploreLeague; winner?: { name: string; logo: string | null } | null } = $props()
  let failed = $state('')
  const upcoming = $derived(!league.first_game && !!league.start_date && Date.parse(`${league.start_date}T00:00:00Z`) > Date.now())
  // a card with a winner slot is on Recently finished: Liquipedia's end date passed, whatever the last game says
  const status = $derived(winner !== undefined ? STATUS.finished : upcoming ? 'Upcoming' : STATUS[league.status])
  async function toggle() {
    try {
      await subscribe(league, !league.subscribed)
      failed = ''
    } catch (e) {
      failed = (e as Error).message
    }
  }
</script>

<article style:--tier={TIER_COLOR[tierGroup(league.lp_tier)]}>
  <header>
    <a class="name" href="#league/{league.league_id}">{league.name}</a>
    <span class="status" class:live={league.status === 'live'}>{status}</span>
  </header>
  <p class="facts">
    {#if league.lp_tier}<span>Tier {league.lp_tier}</span>{/if}
    {#if league.prize_usd}<span>{money(league.prize_usd)}</span>{/if}
    {#if league.games}<span>{league.games} games</span>{/if}
  </p>
  <p class="muted">{dates(league)}{league.location ? `, ${league.location}` : ''}</p>
  {#if winner !== undefined}
    <p class="winner">
      {#if winner}
        {#if winner.logo}<img src={winner.logo} alt="" width="22" height="22" />{/if}
        <span>Won by <strong>{winner.name}</strong></span>
      {:else}
        <span class="muted">Winner not known</span>
      {/if}
    </p>
  {/if}
  <footer>
    <button class="action" aria-pressed={league.subscribed} onclick={toggle}>{league.subscribed ? 'Subscribed ✓' : 'Subscribe'}</button>
    {#if failed}<span class="error" role="alert">{failed}</span>{/if}
  </footer>
</article>

<style>
  article {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 12px 14px;
    border-radius: 6px;
    border-left: 3px solid var(--tier);
    background: var(--surface);
  }
  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
  }
  .name {
    font-weight: 600;
    color: var(--text);
    text-decoration: none;
  }
  .name:hover {
    text-decoration: underline;
  }
  .status {
    flex: none;
    font-size: 12px;
    color: var(--muted);
  }
  .status.live {
    color: var(--good);
    font-weight: 600;
  }
  .status.live::before {
    content: '';
    display: inline-block;
    width: 7px;
    height: 7px;
    margin-right: 5px;
    border-radius: 50%;
    background: var(--good);
    animation: pulse 1.6s ease-in-out infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.3;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .status.live::before {
      animation: none;
    }
  }
  p {
    margin: 0;
    font-size: 13px;
  }
  .facts {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  .winner {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .winner img {
    object-fit: contain;
  }
  footer {
    margin-top: auto;
    padding-top: 4px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
</style>
