<script lang="ts">
  import { follow, progress } from './poller.svelte'

  const STEPS: Record<string, string> = {
    accounts: 'New matches of the accounts', leagues: 'New league games', usual: 'Usual games of checked players',
    folder: 'Replays in the Dota client folder', salts: 'Replay ids from Valve', downloads: 'Replay downloads and parsing',
    players: 'Game lists of league players', stats: 'Stats of parsed matches',
  }
  $effect(() => follow())

  const p = $derived(progress.now)
  const all = $derived(p ? p.overall.parsed + p.overall.waiting : 0)
  const share = (done: number, total: number) => (total ? (100 * done) / total : 100)
  const n = (x: number) => x.toLocaleString()
  const until = (at: number) => {
    const s = Math.max(0, Math.round(at - p!.now))
    return s < 60 ? `${s} s` : `${Math.round(s / 60)} min`
  }
</script>

{#snippet bar(name: string, done: number, total: number)}
  <li>
    <span class="name" title={name}>{name}</span>
    <span class="track" aria-hidden="true"><span class="fill" style:width="{share(done, total)}%"></span></span>
    <span class="count">{n(done)} / {n(total)}</span>
  </li>
{/snippet}

{#if p}
  <!-- focusable, so the overview opens from the keyboard too, not only on hover -->
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="progress" class:busy={p.busy} tabindex="0" aria-label="What runs in the background">
    <div class="track top" role="progressbar" aria-label="Replays parsed" aria-valuemin={0} aria-valuemax={all} aria-valuenow={p.overall.parsed}>
      <span class="fill" style:width="{share(p.overall.parsed, all)}%"></span>
    </div>
    <p class="line muted">
      <span>Replays {n(p.overall.parsed)} / {n(all)} parsed</span>
      {#if p.working.length}<span class="now">{p.working.length} being downloaded and parsed</span>{/if}
      <span>
        {#if p.busy}Poll running: {p.doing}{:else if p.next_poll}Next poll in {until(p.next_poll)}{:else}{p.doing}{/if}
      </span>
    </p>
    <div class="panel card">
      <p class="muted">{p.busy ? `Now: ${p.doing}` : 'No poll running'}{#if p.working.length}. Replays under way:
        {#each p.working as id, i}{i ? ', ' : ''}<a href="#match/{id}">{id}</a>{/each}{/if}</p>
      {#if Object.keys(p.jobs).length}
        <h3>This poll</h3>
        <ul>{#each Object.entries(p.jobs) as [key, job]}{@render bar(STEPS[key] ?? key, job.done, job.total)}{/each}</ul>
      {/if}
      {#if p.profiles.length}
        <h3>Profiles <span class="muted">replays parsed / to get</span></h3>
        <ul>{#each p.profiles as a}{@render bar(a.name ?? String(a.account_id), a.parsed, a.parsed + a.waiting)}{/each}</ul>
      {/if}
      {#if p.tournaments.length}
        <h3>Tournaments</h3>
        <ul>{#each p.tournaments as t}{@render bar(t.name, t.parsed, t.parsed + t.waiting)}{/each}</ul>
      {/if}
      <p class="muted">Replays older than {p.max_age_days} days that never came count in neither number. Details on the <a href="#queue">Queue</a> page.</p>
    </div>
  </div>
{/if}

<style>
  .progress {
    position: relative;
    margin: -8px 0 8px;
    outline-offset: 2px;
  }
  .track {
    display: block;
    height: 4px;
    border-radius: 2px;
    background: var(--grid);
    overflow: hidden;
  }
  .track.top {
    height: 6px;
  }
  .fill {
    display: block;
    height: 100%;
    background: var(--series-1);
    transition: width 0.6s ease;
  }
  .busy .top .fill {
    background: linear-gradient(90deg, var(--series-1) 40%, #8bbcf5 50%, var(--series-1) 60%) 0 0 / 200% 100%;
    animation: sweep 1.6s linear infinite;
  }
  @keyframes sweep {
    to {
      background-position: -200% 0;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .busy .top .fill {
      animation: none;
    }
  }
  .line {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 16px;
    margin: 4px 0 0;
    font-size: 0.85em;
  }
  .now {
    color: var(--series-1);
  }
  .panel {
    display: none;
    position: absolute;
    z-index: 10;
    top: 100%;
    left: 0;
    width: min(560px, 100%);
    max-height: 70vh;
    overflow-y: auto;
    padding: 4px 16px 8px;
    border: 1px solid var(--border);
    margin-top: 4px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
  }
  .progress:hover .panel,
  .progress:focus-within .panel {
    display: block;
  }
  h3 {
    margin: 12px 0 6px;
    font-size: 0.9em;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: grid;
    grid-template-columns: minmax(0, 14em) 1fr auto;
    align-items: center;
    gap: 10px;
    padding: 2px 0;
    font-size: 0.85em;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
</style>
