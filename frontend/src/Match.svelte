<script lang="ts">
  import { GAME_MODES, LOBBY_TYPES, clock, get, type MatchDetail, type MatchPlayer } from './lib/api'
  import Chart, { type Ink } from './lib/Chart.svelte'
  import { constants, heroIcon, heroName, heroPortrait, itemIcon, itemIconByName } from './lib/constants.svelte'
  import Hero from './lib/Hero.svelte'
  import MiniMap, { mapX, mapY, viewOf } from './lib/MiniMap.svelte'
  import Playback from './lib/Playback.svelte'

  let { id }: { id: string } = $props()
  let match = $state<MatchDetail | null>(null)
  let error = $state('')

  $effect(() => {
    let current = true
    match = null
    open = []
    hidden = []
    period = null
    watching = null
    played = []
    get<MatchDetail>(`matches/${id}`).then(
      (found) => current && ((match = found), (error = '')),
      (e) => current && (error = e.message),
    )
    return () => (current = false)
  })

  const TEAMS = ['Radiant', 'Dire'] as const
  const isRadiant = (slot: number) => slot < 128
  const teamOf = (slot: number) => (isRadiant(slot) ? 'radiant' : 'dire')
  const number = (n: number | null | undefined) => (n == null ? '–' : n.toLocaleString()) // Steam omits some stats for older matches
  const thousands = (n: number) => (n === 0 ? '0' : `${Math.round(n / 100) / 10}k`)
  const sum = (values: number[]) => values.reduce((a, b) => a + b, 0)

  const players = $derived(match?.players ?? [])
  const teams = $derived([players.filter((p) => isRadiant(p.player_slot)), players.filter((p) => !isRadiant(p.player_slot))])
  const hero = $derived(new Map(players.map((p) => [p.player_slot, p.hero_id])))
  const name = (slot: number | null) => (slot === null ? '' : heroName(hero.get(slot) ?? 0))
  const hasReplay = $derived(!!match?.player_minute.length)
  const lastMinute = $derived(Math.max(0, ...(match?.player_minute ?? []).map((r) => r.minute)))
  const minuteRow = $derived(new Map((match?.player_minute ?? []).map((r) => [`${r.player_slot}:${r.minute}`, r])))

  // ---- net worth: every hero in one chart. Ten lines need two signs each: the colour is the hero's place in its
  // team, and Dire's lines are dashed. The heroes above the chart are its legend and switch lines off and on.
  let hidden = $state<number[]>([]) // player slots taken out of the chart
  /** The list without `n` if it is in it, with `n` if not. */
  const flip = (list: number[], n: number) => (list.includes(n) ? list.filter((o) => o !== n) : [...list, n])
  const pick = (slot: number) => (hidden = flip(hidden, slot))
  function netWorth(ink: Ink) {
    const rows = match!.player_minute
    const radiant = new Set(teams[0].map((p) => heroName(p.hero_id)))
    const series = teams.flatMap((team, t) =>
      team
        .map((p, i) => ({ p, color: ink[`series-${i + 1}` as keyof Ink] })) // before the filter: a hero keeps its colour
        .filter(({ p }) => !hidden.includes(p.player_slot))
        .map(({ p, color }) => ({
          type: 'line',
          name: heroName(p.hero_id),
          data: rows.filter((r) => r.player_slot === p.player_slot).map((r) => [r.minute, r.net_worth]),
          showSymbol: false,
          lineStyle: { width: 2, type: t ? 'dashed' : 'solid' },
          itemStyle: { color },
          endLabel: { show: true, formatter: '{a}', color: ink['text-2'], distance: 6 },
          labelLayout: { moveOverlap: 'shiftY' },
          emphasis: { focus: 'series' },
        })),
    )
    return {
      animationDuration: 300,
      grid: { left: 48, right: 132, top: 12, bottom: 28 },
      xAxis: {
        type: 'value',
        min: 0,
        max: lastMinute,
        minInterval: 5,
        axisLabel: { color: ink.muted, formatter: '{value}:00' },
        axisLine: { lineStyle: { color: ink.axis } },
        splitLine: { show: false },
      },
      // no fixed top: the scale follows the heroes that are shown
      yAxis: {
        type: 'value',
        min: 0,
        axisLabel: { color: ink.muted, formatter: (v: number) => thousands(v) },
        splitLine: { lineStyle: { color: ink.grid } },
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: { seriesName: string; marker: string; value: [number, number] }[]) =>
          `<b>${params[0].value[0]}:00</b>` +
          TEAMS.map((team, t) => {
            const lines = params.filter((p) => radiant.has(p.seriesName) === (t === 0))
            return lines.length === 0
              ? ''
              : `<br><span style="color:${ink['text-2']}">${team}</span>` +
                  lines
                    .sort((a, b) => b.value[1] - a.value[1])
                    .map((p) => `<br>${p.marker}${p.seriesName} <b style="float:right;margin-left:16px">${number(p.value[1])}</b>`)
                    .join('')
          }).join(''),
      },
      series,
    }
  }

  // ---- leads: Radiant's total minus Dire's, for the whole teams and for each lane
  type Lead = { net_worth: number; xp: number }
  const MEASURES = [
    ['net_worth', 'Net worth'],
    ['xp', 'Experience'],
  ] as const
  const ahead = (v: number) => (v === 0 ? 'even' : `${v > 0 ? 'Radiant' : 'Dire'} +${number(Math.abs(v))}`)
  /** Radiant's lead among these players at each minute from 0 to `minutes`. */
  function leadOf(group: MatchPlayer[], minutes: number): Lead[] {
    return Array.from({ length: minutes + 1 }, (_, minute) => {
      const lead = { net_worth: 0, xp: 0 }
      for (const p of group) {
        const row = minuteRow.get(`${p.player_slot}:${minute}`)
        const sign = isRadiant(p.player_slot) ? 1 : -1
        if (row) (lead.net_worth += sign * row.net_worth), (lead.xp += sign * row.xp)
      }
      return lead
    })
  }
  /** Adds the point where a series crosses zero, so a fill clipped at zero ends exactly on the line. */
  function withCrossings(points: number[][]): number[][] {
    return points.flatMap(([x, v], i) => {
      const next = points[i + 1]
      return next && v * next[1] < 0 ? [[x, v], [x + (next[0] - x) * (v / (v - next[1])), 0]] : [[x, v]]
    })
  }
  /** A lead over time: net worth and experience in their own panels (different units). `bound` fixes both scales,
   *  so charts drawn side by side can be compared. */
  function leadChart(lead: Lead[], bound?: number) {
    const last = lead.length - 1
    return (ink: Ink) => ({
      title: MEASURES.map(([, text], i) => ({
        text,
        left: 48,
        top: i ? '52%' : 0,
        textStyle: { color: ink['text-2'], fontSize: 12, fontWeight: 600 },
      })),
      grid: [
        { left: 48, right: 16, top: 26, bottom: '54%' },
        { left: 48, right: 16, top: '58%', bottom: 28 },
      ],
      xAxis: [0, 1].map((gridIndex) => ({
        type: 'value',
        gridIndex,
        min: 0,
        max: last,
        minInterval: last > 15 ? 5 : 2,
        axisLabel: { show: gridIndex === 1, color: ink.muted, formatter: '{value}:00' },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      })),
      yAxis: [0, 1].map((gridIndex) => ({
        type: 'value',
        gridIndex,
        min: bound && -bound,
        max: bound,
        axisLabel: { color: ink.muted, formatter: (v: number) => thousands(Math.abs(v)) },
        splitLine: { lineStyle: { color: ink.grid } },
      })),
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      tooltip: {
        trigger: 'axis',
        formatter: (params: { axisValue: number }[]) => {
          const minute = Math.min(last, Math.round(params[0].axisValue)) // a fill may add a point between minutes
          return `<b>${minute}:00</b><br>Net worth: ${ahead(lead[minute].net_worth)}<br>Experience: ${ahead(lead[minute].xp)}`
        },
      },
      // the sign carries the meaning, so the fill colour follows it; the line itself stays neutral
      series: MEASURES.flatMap(([key, text], i) => {
        const points = withCrossings(lead.map((at, minute) => [minute, at[key]]))
        const panel = { type: 'line', xAxisIndex: i, yAxisIndex: i, showSymbol: false }
        const fill = (name: string, color: string, part: (v: number) => number) => ({
          ...panel,
          name,
          data: points.map(([x, v]) => [x, part(v)]),
          lineStyle: { width: 0 },
          areaStyle: { color, opacity: 0.4 },
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
    })
  }

  // ---- laning: each lane once, Radiant's heroes against Dire's, up to 10:00 (or the end of a shorter game)
  const LANES = { top: 'Top', mid: 'Mid', bot: 'Bottom', jungle: 'Jungle' } as const
  const LANE_ORDER = Object.keys(LANES)
  const laneMinute = $derived(Math.min(10, lastMinute))
  const laneOf = $derived(new Map((match?.lanes ?? []).map((l) => [l.player_slot, l.lane])))
  const lanes = $derived(
    (['top', 'mid', 'bot'] as const).map((lane) => {
      const there = players.filter((p) => laneOf.get(p.player_slot) === lane)
      const sides = [there.filter((p) => isRadiant(p.player_slot)), there.filter((p) => !isRadiant(p.player_slot))]
      // a lead needs both sides in the lane
      return { lane, sides, lead: sides[0].length && sides[1].length ? leadOf(there, laneMinute) : null }
    }),
  )
  /** One scale for every lane chart: the largest lead in any lane, rounded up to a full thousand. */
  const laneBound = $derived(
    Math.max(1000, Math.ceil(Math.max(...lanes.flatMap((l) => (l.lead ?? []).flatMap((at) => [Math.abs(at.net_worth), Math.abs(at.xp)]))) / 1000) * 1000),
  )
  const laneRank = (p: MatchPlayer) => (LANE_ORDER.indexOf(laneOf.get(p.player_slot) ?? '') + 9) % 9 // no lane sorts last
  const byLane = (team: MatchPlayer[]) => [...team].sort((a, b) => laneRank(a) - laneRank(b))

  // ---- purchases on a timeline, without what is bought over and over
  const UNLISTED = new Set([
    'tango', 'tango_single', 'clarity', 'flask', 'enchanted_mango', 'famango', 'faerie_fire', 'tpscroll',
    'ward_observer', 'ward_sentry', 'ward_dispenser', 'smoke_of_deceit', 'dust', 'blood_grenade', 'tome_of_knowledge',
  ]) // prettier-ignore
  const itemName = (item: string) => item.replaceAll('_', ' ')
  // seconds; a part that went into a bigger item this soon after it was bought is not shown. The starting items are
  // always shown
  const BUILT_SOON = 60
  const ICON = 29 // px one item takes on the timeline, gap included
  const ROW = 23
  let trackWidth = $state(0)
  const span = $derived(Math.max(match?.duration ?? 0, ...(match?.purchases ?? []).map((b) => b.time), 1))
  const timeX = (seconds: number) => (seconds / span) * Math.max(trackWidth - ICON, 0)
  const ticks = $derived(Array.from({ length: Math.floor(span / 600) + 1 }, (_, i) => i * 600))
  /** A player's build: what was bought before the horn, and everything after placed by time. Items bought too close
   *  together to sit side by side move down a row. */
  function timeline(slot: number) {
    const build = match!.purchases.filter(
      (b) =>
        b.player_slot === slot &&
        !UNLISTED.has(b.item) &&
        !b.item.startsWith('recipe') &&
        !(b.time >= 0 && b.built_at !== null && b.built_at - b.time <= BUILT_SOON),
    )
    const rowEnds: number[] = []
    const placed = build
      .filter((b) => b.time >= 0)
      .map((b) => {
        const x = timeX(b.time)
        let row = rowEnds.findIndex((end) => end <= x)
        if (row < 0) row = rowEnds.length
        rowEnds[row] = x + ICON
        return { ...b, x, row }
      })
    return { start: build.filter((b) => b.time < 0), placed, rows: Math.max(1, rowEnds.length) }
  }

  // ---- the two maps: the whole game, or ten minutes of it
  type Ward = MatchDetail['wards'][number]
  type Death = MatchDetail['deaths'][number]
  let period = $state<number | null>(null) // first minute of the ten shown; null is the whole game
  const periods = $derived(Array.from({ length: Math.max(1, Math.ceil((match?.duration ?? 0) / 600)) }, (_, i) => i * 10))
  /** What happened before the horn belongs to the first ten minutes. */
  const inPeriod = (time: number) => period === null || (Math.max(time, 0) >= period * 60 && time < (period + 10) * 60)
  const wardsShown = $derived((match?.wards ?? []).filter((w) => inPeriod(w.placed)))
  const deathsShown = $derived((match?.deaths ?? []).filter((d) => d.x !== null && inPeriod(d.time)))
  const standing = (w: Ward, time: number) => w.placed <= time && (w.removed === null || w.removed > time)

  const WARD = { obs: 'Observer', sen: 'Sentry' }
  function wardNote(w: Ward) {
    const fate =
      w.removed === null
        ? 'still up at the end'
        : !w.killed
          ? `expired ${clock(w.removed)}`
          : `destroyed ${clock(w.removed)}${w.killed_by === null ? '' : ` by ${name(w.killed_by)}`}`
    return `${WARD[w.type]} by ${name(w.player_slot)}, placed ${clock(w.placed)}, ${fate}`
  }
  const deathNote = (d: Death) =>
    `${name(d.player_slot)} died at ${clock(d.time)}` +
    (d.killer_slot === null ? '' : `, killed by ${name(d.killer_slot)}`) +
    (d.in_teamfight ? ' (teamfight)' : '')
  const fightPlayers = (n: number, radiant: boolean) =>
    match!.teamfight_players.filter((p) => p.n === n && isRadiant(p.player_slot) === radiant)

  // ---- fights: the first ten minutes are laning, and three deaths there are a skirmish in a lane
  const FIGHTS_FROM = 600
  const fights = $derived((match?.teamfights ?? []).filter((f) => f.start >= FIGHTS_FROM))
  let open = $state<number[]>([])
  const toggle = (n: number) => (open = flip(open, n))
  const signed = (n: number) => (n > 0 ? '+' : n < 0 ? '−' : '') + number(Math.abs(n))
  const GAINS = [
    ['net_worth_gain', 'Net worth'],
    ['xp_gain', 'Experience'],
  ] as const
  /** What Radiant gained during the fight minus what Dire gained. */
  const swing = (n: number, key: (typeof GAINS)[number][0]) =>
    sum(fightPlayers(n, true).map((p) => p[key])) - sum(fightPlayers(n, false).map((p) => p[key]))
  /** The largest swing of any fight shown, per measure: the scale of the swing bars. */
  const swingBound = $derived(GAINS.map(([key]) => Math.max(1, ...fights.map((f) => Math.abs(swing(f.n, key))))))
  const fallen = (fight: MatchDetail['teamfights'][number]) =>
    match!.deaths.filter((d) => d.x !== null && d.time >= fight.start && d.time <= fight.end)

  // ---- playback (lib/Playback.svelte): the 20 seconds before a death, or a whole fight
  const REPLAY = 20 // seconds shown before a death
  let watching = $state.raw<Death | null>(null)
  let played = $state<number[]>([]) // fights whose playback is shown
</script>

{#snippet side(team: MatchPlayer[], won: boolean)}
  <div class="side" class:lost={!won}>
    {#each team as p (p.player_slot)}
      <figure class={teamOf(p.player_slot)}>
        <img src={heroPortrait(p.hero_id)} alt={heroName(p.hero_id)} title={heroName(p.hero_id)} width="256" height="144" />
        {#if p.label}<figcaption>{p.label}</figcaption>{/if}
      </figure>
    {/each}
  </div>
{/snippet}

{#snippet icons(team: MatchPlayer[])}
  {#each team as p (p.player_slot)}
    <img src={heroIcon(p.hero_id)} alt={heroName(p.hero_id)} title={heroName(p.hero_id)} width="28" height="28" loading="lazy" />
  {/each}
{/snippet}

{#snippet wardMark(w: Ward, r: number, tone: string)}
  {@const x = mapX(w.x)}
  {@const y = mapY(w.y)}
  <g>
    <title>{wardNote(w)}</title>
    {#if w.type === 'obs'}
      <circle class="mark {teamOf(w.player_slot)} {tone}" cx={x} cy={y} {r} stroke-width={r * 0.26} />
    {:else}
      <rect
        class="mark {teamOf(w.player_slot)} {tone}"
        x={x - r * 0.82}
        y={y - r * 0.82}
        width={r * 1.64}
        height={r * 1.64}
        stroke-width={r * 0.26}
        transform="rotate(45 {x} {y})"
      />
    {/if}
  </g>
{/snippet}

{#snippet wardsAt(time: number, size: number)}
  {#each (match?.wards ?? []).filter((w) => standing(w, time)) as w}{@render wardMark(w, size * 0.025, '')}{/each}
{/snippet}

{#snippet fallenMark(d: Death, icon: number)}
  {@const x = mapX(d.x!)}
  {@const y = mapY(d.y!)}
  <g class="fallen {teamOf(d.player_slot)}">
    <title>{deathNote(d)}</title>
    <circle cx={x} cy={y} r={icon * 0.62} stroke-width={icon * 0.1} />
    <image href={heroIcon(hero.get(d.player_slot) ?? 0)} x={x - icon / 2} y={y - icon / 2} width={icon} height={icon} />
  </g>
{/snippet}

{#snippet party(n: number, radiant: boolean)}
  {#each fightPlayers(n, radiant) as p (p.player_slot)}
    <img
      src={heroIcon(hero.get(p.player_slot) ?? 0)}
      alt="{name(p.player_slot)}{p.took_part ? '' : ' (not in the fight)'}"
      title="{name(p.player_slot)}: {number(p.damage)} damage, {p.deaths} deaths{p.took_part ? '' : ', not in the fight'}"
      class:absent={!p.took_part}
      width="24"
      height="24"
      loading="lazy"
    />
  {/each}
{/snippet}

<p class="back"><a href="#matches">← Matches</a></p>
{#if error}
  <p class="error" role="alert">{error}</p>
{:else if match}
  <header class="faceoff">
    {@render side(teams[0], match.radiant_win)}
    <div class="score">
      <p class="kills">
        <b class="radiant">{sum(teams[0].map((p) => p.kills))}</b>
        <span>{clock(match.duration)}</span>
        <b class="dire">{sum(teams[1].map((p) => p.kills))}</b>
      </p>
      <p class="result">{match.radiant_win ? 'Radiant' : 'Dire'} victory</p>
      <p class="muted">
        {LOBBY_TYPES[match.lobby_type] ?? `Lobby ${match.lobby_type}`}
        {GAME_MODES[match.game_mode] ?? `Mode ${match.game_mode}`},
        {new Date(match.start_time * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
        <br />match {match.match_id}
      </p>
    </div>
    {@render side(teams[1], !match.radiant_win)}
  </header>

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
          <tr class="team {i ? 'dire' : 'radiant'}">
            <th colspan="9">{TEAMS[i]}{#if match.radiant_win === (i === 0)}<span class="tag">Winner</span>{/if}</th>
          </tr>
          {#each team as p (p.player_slot)}
            <tr class={teamOf(p.player_slot)}>
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
    <h2>Team lead</h2>
    <p class="legend">
      <span><i class="swatch radiant"></i>Radiant ahead</span>
      <span><i class="swatch dire"></i>Dire ahead</span>
    </p>
    <div class="card chart">
      <Chart option={leadChart(leadOf(players, lastMinute))} height={320} label="Radiant's lead over Dire in net worth and in experience over time; above zero Radiant is ahead, below zero Dire" />
    </div>

    <h2>Net worth by hero</h2>
    <p class="muted">Click a hero to take its line out of the chart, and again to put it back. Dire's lines are dashed.</p>
    <div class="pick">
      {#each teams as team, t}
        <div class={t ? 'dire' : 'radiant'} role="group" aria-label="{TEAMS[t]} heroes in the chart">
          <span>{TEAMS[t]}</span>
          {#each team as p, i (p.player_slot)}
            <button aria-pressed={!hidden.includes(p.player_slot)} onclick={() => pick(p.player_slot)} title={heroName(p.hero_id)}>
              <img src={heroIcon(p.hero_id)} alt={heroName(p.hero_id)} width="28" height="28" />
              <i class:dashed={t === 1} style:border-color="var(--series-{i + 1})"></i>
            </button>
          {/each}
        </div>
      {/each}
    </div>
    <div class="card chart">
      <Chart option={netWorth} height={380} label="Net worth over time of the heroes chosen above; the laning table below has the numbers at 10 minutes" />
    </div>

    <h2>Laning, first {laneMinute} minutes</h2>
    <p class="muted">
      A hero's lane is where it spent most of that time. Each chart is the lane's Radiant heroes together against its Dire
      heroes, all three on one scale.
    </p>
    <div class="lanes">
      {#each lanes as { lane, sides, lead } (lane)}
        {@const now = lead?.[laneMinute]}
        <section class="card lane">
          <h3>{LANES[lane]}</h3>
          <div class="versus">
            <span class="heroes">{@render icons(sides[0])}</span>
            <span class="tug" aria-hidden="true">
              <span><i class="radiant" style:width="{now ? (100 * Math.max(now.net_worth, 0)) / laneBound : 0}%"></i></span>
              <span><i class="dire" style:width="{now ? (100 * Math.max(-now.net_worth, 0)) / laneBound : 0}%"></i></span>
            </span>
            <span class="heroes">{@render icons(sides[1])}</span>
          </div>
          {#if lead && now}
            <p class="standing">{ahead(now.net_worth)} net worth, {ahead(now.xp)} experience at {laneMinute}:00</p>
            <Chart option={leadChart(lead, laneBound)} height={230} label="{LANES[lane]} lane: Radiant's lead over Dire in net worth and experience, minute by minute" />
          {:else}
            <p class="standing muted">{sides[0].length || sides[1].length ? 'Only one team had heroes in this lane.' : 'No hero spent the laning stage here.'}</p>
          {/if}
        </section>
      {/each}
    </div>

    <div class="card">
      <table>
        <thead>
          <tr>
            <th>Hero at {laneMinute}:00</th><th>Lane</th><th class="num">Last hits</th><th class="num">Denies</th>
            <th class="num">Net worth</th><th class="num">Experience</th><th class="num">Camps stacked</th><th class="num">Lotuses used</th>
          </tr>
        </thead>
        <tbody>
          {#each teams as team}
            {#each byLane(team) as p (p.player_slot)}
              {@const at = minuteRow.get(`${p.player_slot}:${laneMinute}`)}
              {@const lane = laneOf.get(p.player_slot)}
              <tr class={teamOf(p.player_slot)}>
                <td><Hero id={p.hero_id} /></td>
                <td>{lane ? LANES[lane as keyof typeof LANES] : '–'}</td>
                <td class="num">{number(at?.last_hits)}</td>
                <td class="num">{number(at?.denies)}</td>
                <td class="num">{number(at?.net_worth)}</td>
                <td class="num">{number(at?.xp)}</td>
                <td class="num">{number(at?.camps_stacked)}</td>
                <td class="num">{number(at?.lotuses)}</td>
              </tr>
            {/each}
          {/each}
        </tbody>
      </table>
    </div>

    <h2>Item timeline</h2>
    <p class="muted">
      Each item sits at the time it was bought; hover one for its name and time. A part that went into a bigger item
      within a minute is left out, so only the finished item shows. Consumables, wards and recipes are left out too.
    </p>
    <div class="card timeline" style:--step="{Math.max(timeX(300), 1)}px">
      <span></span>
      <span class="head">Before 0:00</span>
      <span class="head axis" bind:clientWidth={trackWidth}>
        {#each ticks as t}<span style:left="{timeX(t)}px">{clock(t)}</span>{/each}
      </span>
      {#each players as p (p.player_slot)}
        {@const line = timeline(p.player_slot)}
        <span class="owner {teamOf(p.player_slot)}"><Hero id={p.hero_id} /></span>
        <span class="start">
          {#each line.start as b}
            <img src={itemIconByName(b.item)} alt={itemName(b.item)} title="{itemName(b.item)} at {clock(b.time)}" width="27" height="20" loading="lazy" />
          {/each}
        </span>
        <span class="track" style:min-height="{line.rows * ROW}px">
          {#each line.placed as b}
            <img
              src={itemIconByName(b.item)}
              alt="{itemName(b.item)} at {clock(b.time)}"
              title="{itemName(b.item)} at {clock(b.time)}"
              style:left="{b.x}px"
              style:top="{b.row * ROW}px"
              width="27"
              height="20"
              loading="lazy"
            />
          {/each}
        </span>
      {/each}
    </div>

    <h2>Wards and deaths</h2>
    <p class="filters">
      <span class="choice" role="group" aria-label="Part of the game shown on both maps">
        <button aria-pressed={period === null} onclick={() => (period = null)}>Whole game</button>
        {#each periods as from}
          <button aria-pressed={period === from} onclick={() => (period = from)}>{from}–{from + 10} min</button>
        {/each}
      </span>
      <span class="muted">A ward belongs to the ten minutes it was placed in. Hover a mark for details.</span>
    </p>
    <div class="maps">
      <section>
        <h3>Wards placed</h3>
        <p class="legend">
          <span><i class="swatch radiant"></i>Radiant</span>
          <span><i class="swatch dire"></i>Dire</span>
          <span>● Observer</span>
          <span>◆ Sentry</span>
        </p>
        <MiniMap label="Map of the {wardsShown.length} wards placed {period === null ? 'in this match' : `from minute ${period} to ${period + 10}`}">
          {#each wardsShown as w}{@render wardMark(w, 1.7, '')}{/each}
        </MiniMap>
      </section>
      <section>
        <h3>Deaths</h3>
        <p class="legend">
          <span><i class="swatch radiant"></i>green edge: a Radiant hero died</span>
          <span><i class="swatch dire"></i>red edge: a Dire hero died</span>
        </p>
        <MiniMap label="Map of the {deathsShown.length} hero deaths {period === null ? 'in this match' : `from minute ${period} to ${period + 10}`}">
          {#each deathsShown as d}{@render fallenMark(d, 5.5)}{/each}
        </MiniMap>
      </section>
    </div>

    <details class="card replay">
      <summary>Play back a death</summary>
      <div class="playback">
        <ul aria-label="Deaths {period === null ? 'in this match' : `from minute ${period} to ${period + 10}`}">
          {#each deathsShown as d}
            <li>
              <button aria-pressed={watching === d} onclick={() => (watching = d)}>
                <span class="num">{clock(d.time)}</span>
                <img src={heroIcon(hero.get(d.player_slot) ?? 0)} alt="" width="22" height="22" loading="lazy" />
                {name(d.player_slot)}
                {#if d.killer_slot !== null}
                  <img class="killer" src={heroIcon(hero.get(d.killer_slot) ?? 0)} alt="killed by {name(d.killer_slot)}" title="killed by {name(d.killer_slot)}" width="22" height="22" loading="lazy" />
                {/if}
              </button>
            </li>
          {/each}
        </ul>
        <section>
          {#if !watching}
            <p class="muted">
              Choose a death to see the {REPLAY} seconds before it: every hero's position second by second, and the
              wards standing at that moment. The list follows the part of the game chosen above.
            </p>
          {:else}
            <h3>{deathNote(watching)}</h3>
            <Playback
              matchId={id}
              start={watching.time - REPLAY}
              end={watching.time}
              {players}
              points={[watching]}
              follow={watching.player_slot}
              wards={wardsAt}
              label="the {REPLAY} seconds before {name(watching.player_slot)} died"
            />
            <p class="muted">
              Double speed. The hero with the white ring is the one that dies; a faded hero is dead, and one that
              teleports or blinks jumps. Wards as on the map above: ● observer, ◆ sentry.
            </p>
          {/if}
        </section>
      </div>
    </details>

    <h2>Teamfights</h2>
    {#if fights.length === 0}
      <p class="muted">No fight with three or more deaths after 10:00.</p>
    {:else}
      <p class="muted">
        Three or more deaths less than 15 seconds apart, from 10:00 on. Faded heroes neither dealt nor took hero damage
        and did not die. The bar under the time is how much more net worth one team gained in the fight than the other.
        Click a fight to see where it happened and what each hero did.
      </p>
      <div class="card">
        <table class="fights">
          <thead>
            <tr>
              <th class="num">Radiant took part</th><th class="num">Damage</th><th class="num">Deaths</th>
              <th class="when">Time and net worth swing</th>
              <th>Deaths</th><th>Damage</th><th>Dire took part</th>
            </tr>
          </thead>
          <tbody>
            {#each fights as fight (fight.n)}
              {@const radiant = fightPlayers(fight.n, true)}
              {@const dire = fightPlayers(fight.n, false)}
              {@const unfolded = open.includes(fight.n)}
              {@const when = `${clock(fight.start)} – ${clock(fight.end)}`}
              {@const gold = swing(fight.n, 'net_worth_gain')}
              <!-- the button in the row is the keyboard's way in; its click reaches this handler too -->
              <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
              <tr class="fight" class:unfolded onclick={() => toggle(fight.n)}>
                <td class="num party">{@render party(fight.n, true)}</td>
                <td class="num">{number(sum(radiant.map((p) => p.damage)))}</td>
                <td class="num">{sum(radiant.map((p) => p.deaths))}</td>
                <td class="when">
                  <button aria-expanded={unfolded}>{when}</button>
                  <span class="tug" aria-hidden="true">
                    <span><i class="radiant" style:width="{(100 * Math.max(gold, 0)) / swingBound[0]}%"></i></span>
                    <span><i class="dire" style:width="{(100 * Math.max(-gold, 0)) / swingBound[0]}%"></i></span>
                  </span>
                  <span class="swing">{ahead(gold)}</span>
                </td>
                <td>{sum(dire.map((p) => p.deaths))}</td>
                <td>{number(sum(dire.map((p) => p.damage)))}</td>
                <td class="party">{@render party(fight.n, false)}</td>
              </tr>
              {#if unfolded}
                {@const dead = fallen(fight)}
                {@const view = viewOf(dead)}
                {@const icon = view.size * 0.12}
                {@const most = Math.max(1, ...[...radiant, ...dire].flatMap((p) => [p.damage, p.healing]))}
                <tr class="detail">
                  <td colspan="7">
                    <div class="inside">
                      <section>
                        <h3>Swing</h3>
                        {#each GAINS as [key, text], i}
                          {@const v = swing(fight.n, key)}
                          <p class="standing">{text}: {ahead(v)}</p>
                          <span class="tug" aria-hidden="true">
                            <span><i class="radiant" style:width="{(100 * Math.max(v, 0)) / swingBound[i]}%"></i></span>
                            <span><i class="dire" style:width="{(100 * Math.max(-v, 0)) / swingBound[i]}%"></i></span>
                          </span>
                        {/each}
                        <p class="muted">How much more one team gained than the other during the fight. A full bar is the largest swing of this match.</p>
                        <h3>Deaths and wards</h3>
                        <MiniMap label="Where the {dead.length} heroes died in the fight at {when}, and the wards standing there" view="{view.x} {view.y} {view.size} {view.size}">
                          <!-- a ward that stood through the fight is a dark mark on a light one -->
                          {#each match.wards.filter((w) => standing(w, fight.start)) as w}{@render wardMark(w, view.size * 0.04, 'light')}{/each}
                          {#each match.wards.filter((w) => standing(w, fight.end)) as w}{@render wardMark(w, view.size * 0.022, 'dark')}{/each}
                          {#each dead as d}{@render fallenMark(d, icon)}{/each}
                        </MiniMap>
                        <p class="legend wardkey">
                          <span><i class="swatch radiant light"></i><i class="swatch dire light"></i>ward up at {clock(fight.start)}</span>
                          <span><i class="swatch radiant dark"></i><i class="swatch dire dark"></i>ward up at {clock(fight.end)}</span>
                        </p>
                        <button class="action" aria-expanded={played.includes(fight.n)} onclick={() => (played = flip(played, fight.n))}>
                          {played.includes(fight.n) ? 'Close the playback' : 'Play back the fight'}
                        </button>
                      </section>
                      <table>
                        <thead>
                          <tr>
                            <th>Hero</th><th class="wide">Damage to heroes</th><th class="wide">Healing</th>
                            <th class="num">Net worth</th><th class="num">Experience</th>
                          </tr>
                        </thead>
                        <tbody>
                          {#each [...radiant, ...dire] as p (p.player_slot)}
                            <tr class={teamOf(p.player_slot)} class:absent={!p.took_part}>
                              <td><Hero id={hero.get(p.player_slot) ?? 0} /></td>
                              {#each [p.damage, p.healing] as v}
                                <td>
                                  <span class="meter"><span><i style:width="{(100 * v) / most}%"></i></span>{number(v)}</span>
                                </td>
                              {/each}
                              <td class="num">{signed(p.net_worth_gain)}</td>
                              <td class="num">{signed(p.xp_gain)}</td>
                            </tr>
                          {/each}
                        </tbody>
                      </table>
                      {#if played.includes(fight.n)}
                        <section class="played">
                          <h3>Playback, {when}</h3>
                          <Playback
                            matchId={id}
                            start={fight.start}
                            end={Math.min(fight.end, match.duration)}
                            {players}
                            points={dead}
                            wards={wardsAt}
                            label="during the fight at {when}"
                          />
                          <p class="muted">
                            Double speed. A faded hero is dead, and one that teleports or blinks jumps. The wards are those
                            standing at each moment: ● observer, ◆ sentry.
                          </p>
                        </section>
                      {/if}
                    </div>
                  </td>
                </tr>
              {/if}
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
  .back {
    margin: 0 0 12px;
  }

  /* the game's own top bar: Radiant on the left, Dire on the right, the score between them */
  .faceoff {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
    align-items: center;
    gap: 12px 28px;
    margin-bottom: 20px;
  }
  .side {
    display: flex;
    align-items: flex-start;
    gap: 4px;
  }
  .side:first-child {
    justify-content: flex-end;
  }
  .side figure {
    flex: 1 1 0;
    max-width: 104px;
    margin: 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .side img {
    width: 100%;
    height: auto;
  }
  /* the team's bar sits between portrait and name, and is not dimmed with a losing portrait */
  .side figure::before {
    content: '';
    order: 1;
    height: 3px;
  }
  figure.radiant::before {
    background: var(--radiant);
  }
  figure.dire::before {
    background: var(--dire);
  }
  figcaption {
    order: 2;
  }
  .side.lost img {
    filter: saturate(0.35) brightness(0.75);
  }
  figcaption {
    padding: 2px 4px;
    background: var(--surface);
    font-size: 12px;
    font-stretch: var(--narrow);
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .score {
    text-align: center;
  }
  .score p {
    margin: 0;
  }
  .kills {
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 16px;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .kills b {
    font-size: 46px;
    font-weight: 800;
    font-stretch: 125%;
  }
  .kills .radiant {
    color: var(--radiant);
  }
  .kills .dire {
    color: var(--dire);
  }
  .kills span {
    font-size: 16px;
    color: var(--text-2);
  }
  .result {
    font-weight: 700;
    font-stretch: var(--wide);
    padding: 6px 0 2px;
  }
  .score .muted {
    font-size: 13px;
  }
  @media (max-width: 860px) {
    .faceoff {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }
    .score {
      grid-row: 1;
      grid-column: 1 / -1;
    }
    .side:first-child {
      justify-content: flex-start;
    }
  }

  tr.radiant > :first-child,
  tr.team.radiant th {
    box-shadow: inset 3px 0 0 var(--radiant);
  }
  tr.dire > :first-child,
  tr.team.dire th {
    box-shadow: inset 3px 0 0 var(--dire);
  }
  .team th {
    background: var(--page);
    color: var(--text);
    font-size: 14px;
    font-stretch: var(--wide);
  }
  .tag {
    margin-left: 8px;
    padding: 1px 6px;
    border-radius: 3px;
    background: var(--raised);
    color: var(--text-2);
    font-size: 12px;
    font-weight: 500;
    font-stretch: normal;
  }

  .lanes {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 12px;
    margin-bottom: 12px;
  }
  .lane {
    padding: 14px;
  }
  .versus {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 10px;
  }
  .heroes {
    display: flex;
    gap: 3px;
    min-height: 28px;
  }
  /* a rope pulled from the middle: the bar grows towards the side that is ahead in net worth */
  .tug {
    display: grid;
    grid-template-columns: 1fr 1fr;
    height: 8px;
    background: var(--raised);
    border-radius: 2px;
    overflow: hidden;
  }
  .tug span {
    display: flex;
  }
  .tug span:first-child {
    justify-content: flex-end;
    border-right: 1px solid var(--text-2);
  }
  .tug .radiant {
    background: var(--radiant);
  }
  .tug .dire {
    background: var(--dire);
  }
  .standing {
    margin: 8px 0 10px;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }

  .timeline {
    display: grid;
    grid-template-columns: max-content max-content 1fr;
    align-items: center;
    padding: 6px 14px 10px;
  }
  .timeline > * {
    padding: 6px 12px 6px 0;
    border-bottom: 1px solid var(--grid);
    align-self: stretch;
  }
  .head {
    color: var(--muted);
    font-size: 13px;
    font-weight: 600;
    font-stretch: var(--narrow);
  }
  .axis {
    position: relative;
    padding-right: 0;
    font-variant-numeric: tabular-nums;
  }
  .axis span {
    position: absolute;
  }
  .owner {
    display: flex;
    align-items: center;
    padding-left: 10px;
  }
  .owner.radiant {
    box-shadow: inset 3px 0 0 var(--radiant);
  }
  .owner.dire {
    box-shadow: inset 3px 0 0 var(--dire);
  }
  .start {
    display: flex;
    flex-wrap: wrap;
    align-content: center;
    gap: 3px 2px;
    max-width: 90px;
  }
  /* a faint line every five minutes */
  .track {
    position: relative;
    box-sizing: content-box;
    padding-right: 0;
    background-image: repeating-linear-gradient(90deg, var(--grid) 0 1px, transparent 1px var(--step));
  }
  .track img {
    position: absolute;
    margin-top: 6px;
  }
  .timeline img {
    border-radius: 2px;
  }

  .maps {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 0 24px;
  }
  .maps h3 {
    font-size: 15px;
  }
  .mark.radiant,
  .swatch.radiant {
    --team: var(--radiant);
  }
  .mark.dire,
  .swatch.dire {
    --team: var(--dire);
  }
  .mark {
    stroke: #fff;
    fill: var(--team);
  }
  /* in a fight: light for a ward up at its start, dark for one up at its end */
  .mark.light {
    fill: color-mix(in srgb, var(--team) 40%, #fff);
    stroke: var(--team);
  }
  .mark.dark {
    fill: color-mix(in srgb, var(--team) 45%, #000);
  }
  .swatch.light {
    background: color-mix(in srgb, var(--team) 40%, #fff);
  }
  .swatch.dark {
    background: color-mix(in srgb, var(--team) 45%, #000);
  }
  .wardkey {
    margin: 8px 0 0;
    font-size: 13px;
  }
  .wardkey .swatch.radiant {
    margin-right: 2px;
  }

  /* the heroes above the net worth chart: its legend, and the switches for its lines */
  .pick {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 28px;
    margin-bottom: 10px;
  }
  .pick div {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .pick span {
    margin-right: 6px;
    padding-left: 9px;
    color: var(--text-2);
    font-weight: 600;
  }
  .pick .radiant span {
    box-shadow: inset 3px 0 0 var(--radiant);
  }
  .pick .dire span {
    box-shadow: inset 3px 0 0 var(--dire);
  }
  .pick button {
    display: grid;
    justify-items: center;
    gap: 4px;
    padding: 4px 6px 6px;
    background: var(--surface);
    border: 0;
    border-radius: 4px;
    cursor: pointer;
  }
  .pick i {
    width: 28px;
    border-top: 3px solid;
  }
  .pick i.dashed {
    border-top-style: dashed;
  }
  .pick button[aria-pressed='false'] {
    background: none;
  }
  .pick button[aria-pressed='false'] > * {
    opacity: 0.3;
    filter: grayscale(1);
  }

  .fights .when {
    text-align: center;
    color: var(--text-2);
  }
  .when .tug {
    width: 150px;
    background: var(--axis); /* the row turns the colour of the usual track when hovered or unfolded */
    margin: 5px auto 3px;
  }
  .swing {
    display: block;
    font-size: 13px;
  }
  .party img {
    vertical-align: middle;
    margin: 0 1px;
  }
  .party .absent {
    opacity: 0.25;
  }
  .fight {
    cursor: pointer;
  }
  .when button {
    font: inherit;
    color: inherit;
    background: none;
    border: 0;
    padding: 0;
    cursor: pointer;
  }
  /* the mark turns down when the fight is unfolded */
  .when button::after {
    content: '';
    display: inline-block;
    margin-left: 8px;
    border: 4px solid transparent;
    border-left-color: var(--muted);
    border-right-width: 0;
    transition: transform 0.15s;
  }
  .when button[aria-expanded='true']::after {
    transform: rotate(90deg);
  }
  .fight.unfolded td {
    border-bottom-color: transparent;
    background: var(--raised);
  }
  /* an unfolded fight is a well in the card; hovering it lights nothing up */
  .detail td {
    background: none;
  }
  .detail > td {
    padding: 16px;
    background: var(--page);
    white-space: normal;
  }
  .inside {
    display: grid;
    grid-template-columns: 250px minmax(0, 1fr);
    align-items: start;
    gap: 16px 28px;
  }
  .inside .standing {
    margin: 0 0 4px;
  }
  .inside .tug {
    margin-bottom: 10px;
  }
  .inside .muted {
    margin: 0 0 16px;
    font-size: 13px;
  }
  .inside .action {
    margin-top: 12px;
  }
  .played {
    grid-column: 1 / -1;
  }
  .played .muted {
    max-width: 520px;
    margin: 0;
  }
  .inside th.wide {
    width: 28%;
  }
  .inside tr.absent td {
    color: var(--muted);
  }
  .meter {
    display: grid;
    grid-template-columns: minmax(40px, 1fr) 6ch;
    align-items: center;
    gap: 8px;
    text-align: right;
  }
  .meter span {
    display: flex;
    height: 8px;
  }
  .meter i {
    border-radius: 0 2px 2px 0;
  }
  tr.radiant .meter i {
    background: var(--radiant);
  }
  tr.dire .meter i {
    background: var(--dire);
  }
  .fallen circle {
    fill: var(--page);
  }
  .fallen.radiant circle {
    stroke: var(--radiant);
  }
  .fallen.dire circle {
    stroke: var(--dire);
  }

  .replay {
    margin-top: 16px;
  }
  .replay summary {
    padding: 11px 14px;
    font-weight: 600;
    cursor: pointer;
  }
  .playback {
    display: grid;
    grid-template-columns: 250px minmax(0, 1fr);
    align-items: start;
    gap: 16px 28px;
    padding: 4px 14px 14px;
  }
  .playback ul {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 600px;
    overflow-y: auto;
    font-variant-numeric: tabular-nums;
  }
  .playback li button {
    display: flex;
    align-items: center;
    gap: 7px;
    width: 100%;
    padding: 4px 8px;
    font: inherit;
    color: var(--text-2);
    text-align: left;
    background: none;
    border: 0;
    border-radius: 3px;
    cursor: pointer;
  }
  .playback li button[aria-pressed='true'] {
    background: var(--raised);
    color: var(--text);
  }
  .playback li .num {
    min-width: 5ch;
  }
  .playback .killer {
    margin-left: auto;
  }
  .playback h3 {
    margin-top: 0;
    font-size: 15px;
  }
  .playback section .muted {
    max-width: 520px;
    font-size: 13px;
  }
  @media (max-width: 760px) {
    .inside,
    .playback {
      grid-template-columns: minmax(0, 1fr);
    }
    .playback ul {
      max-height: 220px;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .when button::after {
      transition: none;
    }
  }
</style>
