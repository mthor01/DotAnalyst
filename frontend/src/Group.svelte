<script lang="ts">
  import { METRICS, get, percent, queryFor, type Account, type MetricAverage, type TeammateRow } from './lib/api'

  let { query, accounts }: { query: string; accounts: Account[] } = $props()
  let teammates = $state<TeammateRow[][]>([])
  let averages = $state<Record<string, MetricAverage>[]>([])
  let error = $state('')

  $effect(() => {
    let current = true
    Promise.all([
      Promise.all(accounts.map((a) => get<TeammateRow[]>('teammates', queryFor(query, a.account_id)))),
      Promise.all(accounts.map((a) => get<MetricAverage[]>('metric-averages', queryFor(query, a.account_id)))),
    ]).then(
      ([t, m]) =>
        current && ((teammates = t), (averages = m.map((rows) => Object.fromEntries(rows.map((r) => [r.name, r])))), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const label = (a: Account) => a.label ?? String(a.account_id)
  // each pair once: account i's row about account j, for j after i
  const pairs = $derived(
    accounts.flatMap((a, i) =>
      accounts.slice(i + 1).flatMap((b) => {
        const together = teammates[i]?.find((t) => t.account_id === b.account_id)
        return together ? [{ a, b, ...together }] : []
      }),
    ),
  )
  // every parsed match of an account has a kill participation, so its count is the number of parsed matches
  const parsed = (i: number) => averages[i]?.kill_participation?.matches ?? 0
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{:else}
  <h2>Win rate together</h2>
  {#if pairs.length === 0}
    <p class="muted">No two tracked accounts were on the same team for these filters.</p>
  {:else}
    <div class="card">
      <table>
        <thead>
          <tr><th>Pair</th><th class="num">Games together</th><th class="num">Won</th><th class="num">Win rate</th></tr>
        </thead>
        <tbody>
          {#each pairs as pair (`${pair.a.account_id}-${pair.b.account_id}`)}
            <tr>
              <td>{label(pair.a)} + {label(pair.b)}</td>
              <td class="num">{pair.games}</td>
              <td class="num">{pair.wins}</td>
              <td class="num">{percent(pair.wins, pair.games)}%</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  <h2>Metric averages</h2>
  <p class="muted">Averaged over each account's matches with a parsed replay. The pair table above counts every stored match.</p>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          {#each accounts as a}<th class="num">{label(a)}</th>{/each}
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Parsed matches</td>
          {#each accounts as _, i}<td class="num">{parsed(i)}</td>{/each}
        </tr>
        {#each METRICS as m (m.name)}
          <tr>
            <td>{m.label}</td>
            {#each accounts as _, i}
              {@const found = averages[i]?.[m.name]}
              <td class="num" title={found ? `${found.matches} matches` : undefined}>{found ? m.show(found.average) : '–'}</td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
