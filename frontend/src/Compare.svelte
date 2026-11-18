<script lang="ts">
  import { untrack } from 'svelte'
  import { METRICS, get, percent, queryFor, type Account, type MetricAverage, type TeammateRow } from './lib/api'

  let { query, accounts }: { query: string; accounts: Account[] } = $props()
  // the two accounts compared, the first two tracked ones at first
  let chosen = $state(untrack(() => [accounts[0]?.account_id, accounts[1]?.account_id ?? accounts[0]?.account_id]))
  let together = $state<TeammateRow | undefined>()
  let averages = $state<Record<string, MetricAverage>[]>([])
  let error = $state('')

  $effect(() => {
    let current = true
    const [a, b] = chosen
    if (a === undefined || b === undefined) return
    Promise.all([
      get<TeammateRow[]>('teammates', queryFor(query, a)),
      ...[a, b].map((id) => get<MetricAverage[]>('metric-averages', queryFor(query, id))),
    ]).then(
      ([t, ...m]) =>
        current &&
        ((together = (t as TeammateRow[]).find((r) => r.account_id === b)),
        (averages = (m as MetricAverage[][]).map((rows) => Object.fromEntries(rows.map((r) => [r.name, r])))),
        (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const label = (id: number | undefined) => accounts.find((a) => a.account_id === id)?.label ?? String(id)
  // every parsed match of an account has a kill participation, so its count is the number of parsed matches
  const parsed = (i: number) => averages[i]?.kill_participation?.matches ?? 0
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else}
  <div class="pick">
    {#each [0, 1] as i}
      <label>
        {i ? 'with' : 'Compare'}
        <select bind:value={chosen[i]}>
          {#each accounts as a (a.account_id)}<option value={a.account_id}>{a.label ?? a.account_id}</option>{/each}
        </select>
      </label>
    {/each}
  </div>

  {#if chosen[0] !== chosen[1]}
    <p class="muted">
      {#if together}
        On the same team in {together.games} matches, won {together.wins} ({percent(together.wins, together.games)}%).
      {:else}
        Never on the same team for these filters.
      {/if}
    </p>
  {/if}

  <div class="card">
    <table>
      <thead>
        <tr><th>Metric</th><th class="num">{label(chosen[0])}</th><th class="num">{label(chosen[1])}</th></tr>
      </thead>
      <tbody>
        <tr><td>Parsed matches</td><td class="num">{parsed(0)}</td><td class="num">{parsed(1)}</td></tr>
        {#each METRICS as m (m.name)}
          <tr>
            <td>{m.label}</td>
            {#each [0, 1] as i}
              {@const found = averages[i]?.[m.name]}
              <td class="num" title={found ? `${found.matches} matches` : undefined}>{found ? m.show(found.average) : '–'}</td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p class="muted">Averaged over each account's matches with a parsed replay; the games together count every stored match.</p>
{/if}

<style>
  .pick {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 12px;
  }
  .pick label {
    display: flex;
    gap: 8px;
    align-items: center;
  }
</style>
