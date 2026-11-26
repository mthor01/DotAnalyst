<script lang="ts">
  import { STATUS, dates, money, subscribe, tierName, type CatalogRow } from './leagues'

  let { rows, empty }: { rows: CatalogRow[]; empty: string } = $props()
  let failed = $state('')
  async function toggle(r: CatalogRow) {
    try {
      await subscribe(r, !r.subscribed)
      failed = ''
    } catch (e) {
      failed = `${r.name}: ${(e as Error).message}`
    }
  }
</script>

<!-- leagues of the tournament browser, Explore's and Search's: a click on the name opens the tournament page -->
{#if failed}<p class="error" role="alert">{failed}</p>{/if}
<div class="card">
  <table>
    <thead>
      <tr><th>Tournament</th><th>Status</th><th class="num">Liquipedia</th><th class="num">Prize pool</th><th class="num">Games</th><th>When</th><th></th></tr>
    </thead>
    <tbody>
      {#each rows as r (r.league_id)}
        <tr>
          <td><a href="#league/{r.league_id}">{r.name}</a> <span class="muted tier">{tierName(r.tier)}</span></td>
          <td class:live={r.status === 'live'}>{STATUS[r.status]}{r.status === 'live' ? `, ${r.live_games} ${r.live_games === 1 ? 'game' : 'games'}` : ''}</td>
          <td class="num">{r.lp_tier ? `Tier ${r.lp_tier}` : ''}</td>
          <td class="num">{money(r.prize_usd)}</td>
          <td class="num">{r.games ?? ''}</td>
          <td class="muted">{dates(r)}</td>
          <td class="num"><button class="action" aria-pressed={r.subscribed} onclick={() => toggle(r)}>{r.subscribed ? 'Subscribed ✓' : 'Subscribe'}</button></td>
        </tr>
      {:else}
        <tr><td colspan="7" class="muted">{empty}</td></tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .tier {
    font-size: 12px;
    margin-left: 4px;
  }
  .live {
    color: var(--good);
    font-weight: 600;
  }
  .live::before {
    content: '● ';
  }
  button[aria-pressed='true'] {
    color: var(--text-2);
    background: transparent;
    box-shadow: inset 0 0 0 1px var(--border);
  }
  td {
    white-space: nowrap;
  }
  td:first-child {
    white-space: normal;
  }
</style>
