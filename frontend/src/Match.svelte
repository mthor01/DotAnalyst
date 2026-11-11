<script lang="ts">
  import { GAME_MODES, LOBBY_TYPES, clock, get, type MatchDetail, type MatchPlayer } from './lib/api'
  import Chart, { type Ink } from './lib/Chart.svelte'
  import { constants, heroIcon, heroName, itemIcon, itemIconByName } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'
  import MiniMap, { mapX, mapY } from './lib/MiniMap.svelte'

  let { id }: { id: string } = $props()
  let match = $state<MatchDetail | null>(null)
  let error = $state('')

  $effect(() => {
    let current = true
    match = null
    get<MatchDetail>(`matches/${id}`).then(
      (found) => current && ((match = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const TEAMS = ['Radiant', 'Dire'] as const
  const isRadiant = (slot: number) => slot < 128
  const teamOf = (slot: number) => (isRadiant(slot) ? 'radiant' : 'dire')
  const number = (n: number | null) => (n === null ? '–' : n.toLocaleString()) // Steam omits some stats for older matches
  const thousands = (n: number) => (n === 0 ? '0' : `${Math.round(n / 100) / 10}k`)
  const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

  const players = $derived(match?.players ?? [])
  const teams = $derived([players.filter((p) => isRadiant(p.player_slot)), players.filter((p) => !isRadiant(p.player_slot))])
  const hero = $derived(new Map(players.map((p) => [p.player_slot, p.hero_id])))
  const name = (slot: number | null) => (slot === null ? '' : heroName(hero.get(slot) ?? 0))
  const hasReplay = $derived(!!match?.player_minute.length)
  const lastMinute = $derived(Math.max(0, ...(match?.player_minute ?? []).map((r) => r.minute)))

  // ---- net worth: one panel per team, so five lines and five colours each, on one shared scale
  function netWorth(ink: Ink) {
    const rows = match!.player_minute
    const top = Math.ceil(Math.max(...rows.map((r) => r.net_worth)) / 5000) * 5000
    const axisLabel = { color: ink.muted }
    const splitLine = { lineStyle: { color: ink.grid } }
    const series = teams.flatMap((team, panel) =>
      team.map((p, i) => ({
        type: 'line',
        name: heroName(p.hero_id),
        xAxisIndex: panel,
        yAxisIndex: panel,
        data: rows.filter((r) => r.player_slot === p.player_slot).map((r) => [r.minute, r.net_worth]),
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: ink[`series-${i + 1}` as keyof Ink] },
        endLabel: { show: true, formatter: '{a}', color: ink['text-2'], distance: 6 },
        labelLayout: { moveOverlap: 'shiftY' },
        emphasis: { focus: 'series' },
      })),
    )
    return {
      textStyle: { fontFamily: FONT },
      title: TEAMS.map((text, panel) => ({
        text,
        left: panel ? '55%' : '5%',
        top: 0,
        textStyle: { color: ink['text-2'], fontSize: 12, fontWeight: 600 },
      })),
      grid: [
        { left: '5%', right: '60%', top: 30, bottom: 28 },
        { left: '55%', right: '10%', top: 30, bottom: 28 },
      ],
      xAxis: [0, 1].map((gridIndex) => ({
        type: 'value',
        gridIndex,
        min: 0,
        max: lastMinute,
        minInterval: 5,
        axisLabel: { ...axisLabel, formatter: '{value}:00' },
        axisLine: { lineStyle: { color: ink.axis } },
        splitLine: { show: false },
      })),
      yAxis: [0, 1].map((gridIndex) => ({
        type: 'value',
        gridIndex,
        min: 0,
        max: top,
        axisLabel: { ...axisLabel, formatter: (v: number) => thousands(v) },
        splitLine,
      })),
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      tooltip: {
        trigger: 'axis',
        backgroundColor: ink.surface,
        borderColor: ink.grid,
        textStyle: { color: ink.text },
        formatter: (params: { axisIndex: number; seriesName: string; marker: string; value: [number, number] }[]) =>
          `<b>${params[0].value[0]}:00</b>` +
          [0, 1]
            .map(
              (panel) =>
                `<br><span style="color:${ink['text-2']}">${TEAMS[panel]}</span>` +
                params
                  .filter((p) => p.axisIndex === panel)
                  .sort((a, b) => b.value[1] - a.value[1])
                  .map((p) => `<br>${p.marker}${p.seriesName} <b style="float:right;margin-left:16px">${number(p.value[1])}</b>`)
                  .join(''),
            )
            .join(''),
      },
      series,
    }
  }

  // ---- team lead: Radiant total minus Dire total, net worth and XP in their own panels (different units)
  const lead = $derived.by(() => {
    const sums = Array.from({ length: lastMinute + 1 }, () => ({ net_worth: 0, xp: 0 }))
    for (const r of match?.player_minute ?? []) {
      const sign = isRadiant(r.player_slot) ? 1 : -1
      sums[r.minute].net_worth += sign * r.net_worth
      sums[r.minute].xp += sign * r.xp
    }
    return sums
  })
  /** Adds the point where a series crosses zero, so a fill clipped at zero ends exactly on the line. */
  function withCrossings(points: number[][]): number[][] {
    return points.flatMap(([x, v], i) => {
      const next = points[i + 1]
      return next && v * next[1] < 0 ? [[x, v], [x + (next[0] - x) * (v / (v - next[1])), 0]] : [[x, v]]
    })
  }
  function teamLead(ink: Ink) {
    const MEASURES = [
      ['net_worth', 'Net worth'],
      ['xp', 'Experience'],
    ] as const
    const ahead = (v: number) => (v === 0 ? 'even' : `${v > 0 ? 'Radiant' : 'Dire'} +${number(Math.abs(v))}`)
    return {
      textStyle: { fontFamily: FONT },
      title: MEASURES.map(([, text], i) => ({
        text,
        left: 56,
        top: i ? '52%' : 0,
        textStyle: { color: ink['text-2'], fontSize: 12, fontWeight: 600 },
      })),
      grid: [
        { left: 56, right: 24, top: 26, bottom: '54%' },
        { left: 56, right: 24, top: '58%', bottom: 28 },
      ],
      xAxis: [0, 1].map((gridIndex) => ({
        type: 'value',
        gridIndex,
        min: 0,
        max: lastMinute,
        minInterval: 5,
        axisLabel: { show: gridIndex === 1, color: ink.muted, formatter: '{value}:00' },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      })),
      yAxis: [0, 1].map((gridIndex) => ({
        type: 'value',
        gridIndex,
        axisLabel: { color: ink.muted, formatter: (v: number) => thousands(Math.abs(v)) },
        splitLine: { lineStyle: { color: ink.grid } },
      })),
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      tooltip: {
        trigger: 'axis',
        backgroundColor: ink.surface,
        borderColor: ink.grid,
        textStyle: { color: ink.text },
        formatter: (params: { axisValue: number }[]) => {
          const minute = Math.min(lastMinute, Math.round(params[0].axisValue)) // a fill may add a point between minutes
          const at = lead[minute]
          return `<b>${minute}:00</b><br>Net worth: ${ahead(at.net_worth)}<br>Experience: ${ahead(at.xp)}`
        },
      },
      // the sign carries the meaning, so the fill colour follows it; the line itself stays neutral
      series: MEASURES.flatMap(([key, text], i) => {
        const points = withCrossings(lead.map((sum, minute) => [minute, sum[key]]))
        const panel = { type: 'line', xAxisIndex: i, yAxisIndex: i, showSymbol: false }
        const fill = (name: string, color: string, part: (v: number) => number) => ({
          ...panel,
          name,
          data: points.map(([x, v]) => [x, part(v)]),
          lineStyle: { width: 0 },
          areaStyle: { color, opacity: 0.3 },
          silent: true,
        })
        return [
          {
            ...panel,
            name: text,
            data: points,
            lineStyle: { width: 2, color: ink['text-2'] },
            itemStyle: { color: ink['text-2'] },
            markLine: {
              silent: true,
              symbol: 'none',
              lineStyle: { color: ink.axis, type: 'solid', width: 1 },
              label: { show: false },
              data: [{ yAxis: 0 }],
            },
          },
          fill('Radiant ahead', ink.radiant, (v) => Math.max(v, 0)),
          fill('Dire ahead', ink.dire, (v) => Math.min(v, 0)),
        ]
      }),
    }
  }

  // ---- laning: my numbers next to my lane opponent's
  const LANING_MINUTES = [5, 10]
  const LANING_STATS = [
    ['last_hits', 'LH'],
    ['denies', 'DN'],
    ['net_worth', 'NW'],
    ['xp', 'XP'],
  ] as const
  const minuteRow = $derived(new Map((match?.player_minute ?? []).map((r) => [`${r.player_slot}:${r.minute}`, r])))
  const lane = $derived(new Map((match?.lanes ?? []).map((l) => [l.player_slot, l])))

  // ---- purchases: the build, without what is bought over and over
  const UNLISTED = new Set([
    'tango', 'tango_single', 'clarity', 'flask', 'enchanted_mango', 'famango', 'faerie_fire', 'tpscroll',
    'ward_observer', 'ward_sentry', 'ward_dispenser', 'smoke_of_deceit', 'dust', 'blood_grenade', 'tome_of_knowledge',
  ]) // prettier-ignore
  const build = (slot: number) =>
    match!.purchases.filter((b) => b.player_slot === slot && !UNLISTED.has(b.item) && !b.item.startsWith('recipe'))
  const itemName = (item: string) => item.replaceAll('_', ' ')

  // ---- maps and fights
  const WARD = { obs: 'Observer', sen: 'Sentry' }
  function wardNote(w: MatchDetail['wards'][number]) {
    const fate =
      w.removed === null
        ? 'still up at the end'
        : !w.killed
          ? `expired ${clock(w.removed)}`
          : `destroyed ${clock(w.removed)}${w.killed_by === null ? '' : ` by ${name(w.killed_by)}`}`
    return `${WARD[w.type]} by ${name(w.player_slot)}, placed ${clock(w.placed)}, ${fate}`
  }
  const deathNote = (d: MatchDetail['deaths'][number]) =>
    `${name(d.player_slot)} died at ${clock(d.time)}` +
    (d.killer_slot === null ? '' : `, killed by ${name(d.killer_slot)}`) +
    (d.in_teamfight ? ' (teamfight)' : '')
  const fightPlayers = (n: number, radiant: boolean) =>
    match!.teamfight_players.filter((p) => p.n === n && isRadiant(p.player_slot) === radiant)
  const sum = (values: number[]) => values.reduce((a, b) => a + b, 0)
</script>

{#snippet scoreRows(team: MatchPlayer[])}
  {#each team as p (p.player_slot)}
    <tr>
      <td><Hero id={p.hero_id} />{#if p.label}<span class="tag">{p.label}</span>{/if}</td>
      <td class="num">{p.level}</td>
      <td class="num">{p.kills} / {p.deaths} / {p.assists}</td>
      <td class="num">{p.last_hits} / {p.denies}</td>
      <td class="num">{p.gold_per_min}</td>
      <td class="num">{p.xp_per_min}</td>
      <td class="num">{number(p.net_worth)}</td>
      <td class="num">{number(p.hero_damage)}</td>
      <td class="items">
        {#each p.items.filter((item) => item) as item}
          {#if itemIcon(item)}
            <img src={itemIcon(item)} alt={itemName(constants.items[item])} title={itemName(constants.items[item])} width="30" height="22" loading="lazy" />
          {/if}
        {/each}
      </td>
    </tr>
  {/each}
{/snippet}

{#snippet legend()}
  <p class="legend">
    <span><i class="swatch radiant"></i>Radiant</span>
    <span><i class="swatch dire"></i>Dire</span>
  </p>
{/snippet}

<p><a href="#matches">← Matches</a></p>
{#if error}
  <p class="error" role="alert">{error}</p>
{:else if match}
  <h2 class="title">
    {match.radiant_win ? 'Radiant' : 'Dire'} victory
    <span class="muted">
      · {new Date(match.start_time * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
      · {clock(match.duration)}
      · {LOBBY_TYPES[match.lobby_type] ?? `Lobby ${match.lobby_type}`}
      {GAME_MODES[match.game_mode] ?? `Mode ${match.game_mode}`}
      · match {match.match_id}
    </span>
  </h2>

  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Hero</th><th class="num">Level</th><th class="num">K / D / A</th><th class="num">LH / DN</th>
          <th class="num">GPM</th><th class="num">XPM</th><th class="num">Net worth</th><th class="num">Hero damage</th><th>Items</th>
        </tr>
      </thead>
      <tbody>
        {#each teams as team, i}
          <tr class="team"><th colspan="9">{TEAMS[i]}{match.radiant_win === (i === 0) ? ' · won' : ''}</th></tr>
          {@render scoreRows(team)}
        {/each}
      </tbody>
    </table>
  </div>

  {#if !hasReplay}
    <p class="muted">
      No replay data for this match (replay: {match.replay_state}). Replays are fetched for matches up to 30 days old;
      until one is parsed, only the scoreboard above is known.
    </p>
  {:else}
    <h2>Net worth</h2>
    <div class="card chart">
      <Chart option={netWorth} height={340} label="Net worth of each player over time, one panel per team; the laning table below has the numbers at 5 and 10 minutes" />
    </div>

    <h2>Team lead</h2>
    {@render legend()}
    <div class="card chart">
      <Chart option={teamLead} height={320} label="Radiant's lead over Dire in net worth and in experience over time; above zero Radiant is ahead, below zero Dire" />
    </div>

    <h2>Laning</h2>
    <p class="muted">Each player's numbers, then the lane opponent's: the enemy in the same lane with the most last hits at 10:00.</p>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th rowspan="2">Hero</th><th rowspan="2">Lane</th><th rowspan="2">Against</th>
            {#each LANING_MINUTES as minute}<th colspan={LANING_STATS.length} class="group">at {minute}:00</th>{/each}
          </tr>
          <tr>
            {#each LANING_MINUTES as _}{#each LANING_STATS as [, short]}<th class="num">{short}</th>{/each}{/each}
          </tr>
        </thead>
        <tbody>
          {#each players as p (p.player_slot)}
            {@const mine = lane.get(p.player_slot)}
            <tr>
              <td><Hero id={p.hero_id} /></td>
              <td>{mine?.lane ?? '–'}</td>
              <td>{#if mine?.opponent_slot != null}<Hero id={hero.get(mine.opponent_slot) ?? 0} />{:else}–{/if}</td>
              {#each LANING_MINUTES as minute}
                {@const me = minuteRow.get(`${p.player_slot}:${minute}`)}
                {@const them = minuteRow.get(`${mine?.opponent_slot}:${minute}`)}
                {#each LANING_STATS as [key]}
                  <td class="num">{me ? number(me[key]) : '–'}{#if me && them}<span class="versus">{number(them[key])}</span>{/if}</td>
                {/each}
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <h2>Items bought</h2>
    <p class="muted">In buying order with the game time. Consumables, wards and recipes are left out.</p>
    <div class="card">
      <table>
        <tbody>
          {#each players as p (p.player_slot)}
            <tr>
              <td><Hero id={p.hero_id} /></td>
              <td class="build">
                {#each build(p.player_slot) as b}
                  <span class="buy" title="{itemName(b.item)} at {clock(b.time)}">
                    <img src={itemIconByName(b.item)} alt={itemName(b.item)} width="30" height="22" loading="lazy" />{clock(b.time)}
                  </span>
                {/each}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="maps">
      <section>
        <h2>Wards</h2>
        <p class="legend">
          <span><i class="swatch radiant"></i>Radiant</span>
          <span><i class="swatch dire"></i>Dire</span>
          <span>● Observer</span>
          <span>◆ Sentry</span>
          <span class="muted">hover a mark for details</span>
        </p>
        <MiniMap label="Map of the {match.wards.length} wards placed in this match">
          {#each match.wards as w}
            {@const x = mapX(w.x)}
            {@const y = mapY(w.y)}
            {#if w.type === 'obs'}
              <circle class="mark {teamOf(w.player_slot)}" cx={x} cy={y} r="1.7"><title>{wardNote(w)}</title></circle>
            {:else}
              <rect class="mark {teamOf(w.player_slot)}" x={x - 1.4} y={y - 1.4} width="2.8" height="2.8" transform="rotate(45 {x} {y})">
                <title>{wardNote(w)}</title>
              </rect>
            {/if}
          {/each}
        </MiniMap>
      </section>
      <section>
        <h2>Deaths</h2>
        <p class="legend">
          <span><i class="swatch radiant"></i>a Radiant hero died</span>
          <span><i class="swatch dire"></i>a Dire hero died</span>
        </p>
        <MiniMap label="Map of the {match.deaths.length} hero deaths in this match">
          {#each match.deaths.filter((d) => d.x !== null) as d}
            {@const x = mapX(d.x!)}
            {@const y = mapY(d.y!)}
            <g class="cross {teamOf(d.player_slot)}">
              <title>{deathNote(d)}</title>
              <circle cx={x} cy={y} r="2.4" fill="transparent" stroke="none" />
              <path class="halo" d="M{x - 1.5} {y - 1.5}L{x + 1.5} {y + 1.5}M{x - 1.5} {y + 1.5}L{x + 1.5} {y - 1.5}" />
              <path d="M{x - 1.5} {y - 1.5}L{x + 1.5} {y + 1.5}M{x - 1.5} {y + 1.5}L{x + 1.5} {y - 1.5}" />
            </g>
          {/each}
        </MiniMap>
      </section>
    </div>

    <h2>Teamfights</h2>
    {#if match.teamfights.length === 0}
      <p class="muted">No fight with three or more deaths.</p>
    {:else}
      <p class="muted">Three or more deaths less than 15 seconds apart. Faded heroes neither dealt nor took hero damage and did not die.</p>
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              {#each TEAMS as team}<th class="num">{team} deaths</th><th class="num">damage</th><th>took part</th>{/each}
            </tr>
          </thead>
          <tbody>
            {#each match.teamfights as fight (fight.n)}
              <tr>
                <td>{clock(Math.max(0, fight.start))} – {clock(fight.end)}</td>
                {#each [true, false] as radiant}
                  {@const side = fightPlayers(fight.n, radiant)}
                  <td class="num">{sum(side.map((p) => p.deaths))}</td>
                  <td class="num">{number(sum(side.map((p) => p.damage)))}</td>
                  <td class="party">
                    {#each side as p (p.player_slot)}
                      <img
                        src={heroIcon(hero.get(p.player_slot) ?? 0)}
                        alt="{name(p.player_slot)}{p.took_part ? '' : ' (not in the fight)'}"
                        title="{name(p.player_slot)}: {number(p.damage)} damage, {p.deaths} deaths{p.took_part ? '' : ', not in the fight'}"
                        class:absent={!p.took_part}
                        width="22"
                        height="22"
                        loading="lazy"
                      />
                    {/each}
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {/if}
{:else}
  <p class="muted">Loading…</p>
{/if}

<style>
  .title {
    margin-top: 8px;
  }
  .title .muted {
    font-weight: 400;
  }
  .chart {
    padding: 12px;
  }
  .team th {
    background: var(--page);
  }
  .tag {
    margin-left: 8px;
    padding: 1px 6px;
    border-radius: 4px;
    border: 1px solid var(--border);
    color: var(--text-2);
    font-size: 12px;
  }
  .items img,
  .buy img {
    vertical-align: middle;
    border-radius: 3px;
    margin-right: 2px;
  }
  .group {
    text-align: center;
    border-left: 1px solid var(--grid);
  }
  .versus {
    display: inline-block;
    min-width: 3.2em;
    margin-left: 6px;
    color: var(--muted);
  }
  .build {
    white-space: normal;
  }
  .buy {
    display: inline-block;
    margin: 2px 10px 2px 0;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  .maps {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 0 24px;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 16px;
    margin: 0 0 8px;
    color: var(--text-2);
  }
  .swatch {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 2px;
    margin-right: 6px;
  }
  .swatch.radiant {
    background: var(--radiant);
  }
  .swatch.dire {
    background: var(--dire);
  }
  .mark {
    stroke: #fff;
    stroke-width: 0.45;
  }
  .mark.radiant {
    fill: var(--radiant);
  }
  .mark.dire {
    fill: var(--dire);
  }
  .cross path {
    fill: none;
    stroke-width: 0.8;
    stroke-linecap: round;
  }
  .cross .halo {
    stroke: #fff;
    stroke-width: 1.6;
  }
  .cross.radiant path:not(.halo) {
    stroke: var(--radiant);
  }
  .cross.dire path:not(.halo) {
    stroke: var(--dire);
  }
  .party img {
    vertical-align: middle;
    margin-right: 2px;
  }
  .party .absent {
    opacity: 0.25;
  }
</style>
