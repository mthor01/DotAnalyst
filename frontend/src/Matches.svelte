<script lang="ts">
  import { GAME_MODES, LOBBY_TYPES, clock, get, type MatchRow } from './lib/api'
  import { constants, itemIcon } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'
  import ReplaySign from './lib/ReplaySign.svelte'
  import Match from './Match.svelte'

  let { query }: { query: string } = $props()
  let rows = $state<MatchRow[]>([])
  let error = $state('')

  $effect(() => {
    let current = true // a slower, older request must not overwrite a newer one
    get<MatchRow[]>('matches', query).then(
      (found) => current && ((rows = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString('en-GB', { dateStyle: 'medium' })
  const wins = $derived(rows.filter((r) => r.win).length)
  let unfolded = $state<number[]>([])
  const unfold = (id: number) => (unfolded = unfolded.includes(id) ? unfolded.filter((o) => o !== id) : [...unfolded, id])
  // a click anywhere on the row unfolds it, except on its links and buttons, which do their own thing
  const unfoldRow = (e: MouseEvent, id: number) => !(e.target as Element).closest('a, button') && unfold(id)
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else}
  <p class="muted">
    {rows.length} matches{#if rows.length}, {wins} won ({Math.round((100 * wins) / rows.length)}%){/if}
  </p>
  <div class="card tall">
    <table>
      <thead>
        <tr>
          <th></th>
          <th>Date</th>
          <th>Hero</th>
          <th>Result</th>
          <th class="num">K / D / A</th>
          <th class="num">GPM</th>
          <th class="num">XPM</th>
          <th class="num">LH / DN</th>
          <th class="num">Duration</th>
          <th>Items</th>
          <th>Replay</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each rows as r (r.match_id)}
          {@const open = unfolded.includes(r.match_id)}
          <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions (the arrow button is the keyboard way) -->
          <tr class="folds" onclick={(e) => unfoldRow(e, r.match_id)}>
            <td>
              <button class="unfold" aria-expanded={open} aria-label="Details of the match on {date(r.start_time)}" onclick={() => unfold(r.match_id)}>{open ? '▾' : '▸'}</button>
            </td>
            <td class="when">
              {date(r.start_time)}
              <small class="muted">{LOBBY_TYPES[r.lobby_type] ?? `Lobby ${r.lobby_type}`} {GAME_MODES[r.game_mode] ?? `Mode ${r.game_mode}`}</small>
            </td>
            <td><Hero id={r.hero_id} /></td>
            <td><span class="dot {r.win ? 'won' : 'lost'}"></span>{r.win ? 'Won' : 'Lost'}</td>
            <td class="num">{r.kills} / {r.deaths} / {r.assists}</td>
            <td class="num">{r.gold_per_min}</td>
            <td class="num">{r.xp_per_min}</td>
            <td class="num">{r.last_hits} / {r.denies}</td>
            <td class="num">{clock(r.duration)}</td>
            <td class="items">
              {#each r.items.filter((id) => id) as id}
                {#if itemIcon(id)}
                  <img
                    src={itemIcon(id)}
                    alt={constants.items[id].replaceAll('_', ' ')}
                    title={constants.items[id].replaceAll('_', ' ')}
                    width="30"
                    height="22"
                    loading="lazy"
                  />
                {/if}
              {/each}
            </td>
            <td class="muted"><ReplaySign match_id={r.match_id} state={r.replay_state} start_time={r.start_time} /></td>
            <td><a class="open" href="#match/{r.match_id}" title="Open the match" aria-label="Open the match on {date(r.start_time)}">↗</a></td>
          </tr>
          {#if open}<tr class="more"><td colspan="12"><Match id={String(r.match_id)} brief draft={false} /></td></tr>{/if}
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  /* four items a line: the row is two lines tall for the date and mode anyway */
  .items {
    width: 136px;
    white-space: normal;
    line-height: 0;
  }
  .items img {
    margin: 1px 2px 1px 0;
  }
  .when small {
    display: block;
    font-size: 11px;
  }
  .unfold {
    padding: 2px 6px;
    background: none;
    border: 0;
    color: var(--text-2);
    cursor: pointer;
  }
  .more > td {
    padding: 12px 12px 18px;
    background: var(--page);
  }
</style>
