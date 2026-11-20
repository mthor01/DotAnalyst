<script lang="ts">
  import { follow, progress } from './poller.svelte'

  const STEPS: Record<string, string> = {
    accounts: 'New matches of the accounts', leagues: 'New league games', usual: 'Usual games of checked players',
    folder: 'Replays in the Dota client folder', salts: 'Replay ids from Valve', downloads: 'Replay downloads and parsing',
    players: 'Game lists of league players', stats: 'Stats of parsed matches',
  }
  let { current = false }: { current?: boolean } = $props() // whether the Queue page, which it opens, is shown
  $effect(() => follow())

  const p = $derived(progress.now)
  const all = $derived(p ? p.overall.parsed + p.overall.waiting : 0)
  const share = (done: number, total: number) => (total ? (100 * done) / total : 100)
  const n = (x: number) => x.toLocaleString()
  const running = $derived(p ? Object.entries(p.running) : [])
</script>

{#snippet bar(name: string, done: number, total: number)}
  <li>
    <span class="name" title={name}>{name}</span>
    <span class="track" aria-hidden="true"><span class="fill" style:width="{share(done, total)}%"></span></span>
    <span class="count">{n(done)} / {n(total)}</span>
  </li>
{/snippet}

{#if p}
  <!-- the link is focusable, so the overview below opens from the keyboard too, not only on hover -->
  <div class="progress" class:busy={p.busy}>
    <a href="#queue" aria-current={current ? 'page' : undefined} title="Replays parsed: open the Queue page">
      <span class="track top" aria-hidden="true"><span class="fill" style:width="{share(p.overall.parsed, all)}%"></span></span>
      <span class="label">Replays {n(p.overall.parsed)} / {n(all)}</span>
    </a>
    <div class="panel card">
      <p class="muted">{running.length ? 'At work now' : 'No step has work'}{#if p.working.length}. Matches under way:
        {#each p.working as id, i}{i ? ', ' : ''}<a href="#match/{id}">{id}</a>{/each}{/if}</p>
      {#if running.length}
        <ul>
          {#each running as [key, r]}
            {#if r.total}{@render bar(STEPS[key] ?? key, r.done ?? 0, r.total)}
            {:else}<li><span class="name">{STEPS[key] ?? key}</span><span class="doing muted">{r.doing}</span></li>{/if}
          {/each}
        </ul>
      {/if}
      {#if p.profiles.length}
        <h3>Profiles <span class="muted">replays parsed / to get</span></h3>
        <ul>{#each p.profiles as a}{@render bar(a.name ?? String(a.account_id), a.parsed, a.parsed + a.waiting)}{/each}</ul>
      {/if}
      {#if p.tournaments.length}
        <h3>Tournaments</h3>
        <ul>{#each p.tournaments as t}{@render bar(t.name, t.parsed, t.parsed + t.waiting)}{/each}</ul>
      {/if}
      <p class="muted">Replays older than {p.max_age_days} days that never came count in neither number.</p>
    </div>
  </div>
{/if}

<style>
  .progress {
    position: relative;
  }
  .progress > a {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 0;
    color: var(--muted);
    font-size: 0.75em;
    font-variant-numeric: tabular-nums;
    text-decoration: none;
  }
  .progress > a:hover,
  .progress > a[aria-current='page'] {
    color: var(--text);
  }
  .track {
    display: block;
    height: 4px;
    border-radius: 2px;
    background: var(--grid);
    overflow: hidden;
  }
  .track.top {
    width: 96px;
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
  .panel {
    display: none;
    position: absolute;
    z-index: 10;
    top: 100%;
    left: 0;
    width: min(560px, 90vw);
    max-height: 70vh;
    overflow-y: auto;
    padding: 4px 16px 8px;
    border: 1px solid var(--border); /* no gap above it: the pointer on its way down would leave and close it */
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
  }
  /* keyboard focus opens it; a mouse click, which leaves focus on the link, does not keep it open over the Queue page */
  .progress:hover .panel,
  .progress:has(:focus-visible) .panel {
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
  .doing {
    grid-column: 2 / -1;
  }
  .count {
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
</style>
