<script lang="ts">
  import { replaySign } from './poller.svelte'

  let { match_id, state, start_time }: { match_id: number; state: string | null; start_time: number } = $props()
  const sign = $derived(replaySign(match_id, state, start_time))
</script>

{#if sign === 'parsed'}
  Parsed
{:else if sign === 'working'}
  <span class="working" title="The replay is being downloaded and parsed right now"><span class="spinner" aria-hidden="true"></span>Parsing…</span>
{:else if sign === 'waiting'}
  <span title="The poller still means to get this replay">⏳ Waiting</span>
{:else}
  –
{/if}

<style>
  .working {
    color: var(--series-1);
    white-space: nowrap;
  }
  .spinner {
    display: inline-block;
    width: 0.8em;
    height: 0.8em;
    margin-right: 0.4em;
    vertical-align: -0.1em;
    border: 2px solid currentColor;
    border-right-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation-duration: 3s;
    }
  }
</style>
