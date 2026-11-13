<script lang="ts">
  import { GAME_MODES, LOBBY_TYPES, clock, get, type MatchRow } from './lib/api'
  import { constants, itemIcon } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'

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

  const date = (seconds: number) => new Date(seconds * 1000).toLocaleDateString(undefined, { dateStyle: 'medium' })
  const wins = $derived(rows.filter((r) => r.win).length)
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else}
  <p class="muted">
    {rows.length} matches{#if rows.length}, {wins} won ({Math.round((100 * wins) / rows.length)}%){/if}
  </p>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Hero</th>
          <th>Result</th>
          <th class="num">K / D / A</th>
          <th class="num">GPM</th>
          <th class="num">XPM</th>
          <th class="num">LH / DN</th>
          <th class="num">Duration</th>
          <th>Items</th>
          <th>Mode</th>
          <th>Replay</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as r (r.match_id)}
          <tr>
            <td><a href="#match/{r.match_id}">{date(r.start_time)}</a></td>
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
            <td class="muted">
              {LOBBY_TYPES[r.lobby_type] ?? `Lobby ${r.lobby_type}`} · {GAME_MODES[r.game_mode] ?? `Mode ${r.game_mode}`}
            </td>
            <td class="muted">{r.replay_state === 'parsed' ? 'Parsed' : '–'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
