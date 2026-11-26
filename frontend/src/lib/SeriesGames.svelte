<script lang="ts">
  import { clock, get } from './api'
  import { heroIcon, heroName } from './constants.svelte'
  import { moment, type Draft, type LpMatch, type LpOpponent } from './leagues'

  // one series in a small window: its games with result, length and both drafts; a game opens on a click
  let { match, logo, link, onclose }: {
    match: LpMatch
    logo: (teamId: number) => string | null
    link: (matchId: number) => string
    onclose: () => void
  } = $props()

  let dialog: HTMLDialogElement
  let drafts = $state<Map<number, Draft> | null>(null)
  let error = $state('')
  let bans = $state(false)
  const games = $derived(match.maps.filter((m) => m.match_id))
  $effect(() => {
    dialog.showModal()
    dialog.focus()
    const ids = games.map((g) => `ids=${g.match_id}`).join('&')
    get<Draft[]>('drafts', ids).then((found) => (drafts = new Map(found.map((d) => [d.match_id, d]))), (e) => (error = e.message))
  })

  /** Which side of the game the series' first team played: by team id, else Liquipedia's side of the map */
  function firstIsRadiant(d: Draft | undefined, side: string | null) {
    const [a, b] = match.opponents.map((o) => o.team_id)
    if (d && a && d.radiant_team_id === a) return true
    if (d && a && d.dire_team_id === a) return false
    if (d && b && d.radiant_team_id === b) return false
    return side !== 'dire'
  }
  function winner(map: LpMatch['maps'][number], d: Draft | undefined, radiant: boolean): 0 | 1 | null {
    if (map.winner !== null) return map.winner
    if (d?.radiant_win == null) return null
    return d.radiant_win === radiant ? 0 : 1
  }
  const external = (href: string) => href.startsWith('http')
</script>

{#snippet team(o: LpOpponent, end: boolean)}
  {@const src = o.team_id ? logo(o.team_id) : null}
  <span class="team" class:end>
    {#if src}<img {src} alt="" width="36" height="36" />{/if}
    <span class="name">{o.name ?? 'TBD'}</span>
  </span>
{/snippet}

{#snippet heroes(ids: number[] | undefined, small: boolean)}
  <span class="heroes" class:small>
    {#each ids ?? [] as h, i (i)}<img src={heroIcon(h)} alt={heroName(h)} title={heroName(h)} width={small ? 20 : 26} height={small ? 20 : 26} />{/each}
  </span>
{/snippet}

{#snippet badge(won: boolean | null)}
  <span class="badge" class:won={won === true} class:lost={won === false}>{won === null ? '–' : won ? 'W' : 'L'}</span>
{/snippet}

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<dialog bind:this={dialog} {onclose} tabindex="-1" onclick={(e) => e.target === dialog && dialog.close()} aria-label="Games of the series">
  <header>
    <span class="muted when">{match.time ? moment(match.time) : ''}</span>
    <button class="close" onclick={() => dialog.close()} aria-label="Close">×</button>
  </header>
  <div class="score">
    {@render team(match.opponents[0], false)}
    <span class="result">
      <strong>{match.score[0]} : {match.score[1]}</strong>
      {#if match.best_of}<span class="muted">Bo{match.best_of}</span>{/if}
    </span>
    {@render team(match.opponents[1], true)}
  </div>
  {#if error}
    <p class="muted">The games could not be loaded: {error}</p>
  {:else}
    <ol>
      {#each games as map, i (map.match_id)}
        {@const d = drafts?.get(map.match_id!)}
        {@const radiant = firstIsRadiant(d, map.team1side)}
        {@const won = winner(map, d, radiant)}
        {@const picks = d?.picks ? (radiant ? d.picks : [d.picks[1], d.picks[0]]) : null}
        {@const banned = d?.bans ? (radiant ? d.bans : [d.bans[1], d.bans[0]]) : null}
        {@const href = link(map.match_id!)}
        <li>
          <a {href} target={external(href) ? '_blank' : undefined} rel={external(href) ? 'noreferrer' : undefined} title="Game {i + 1}: open the match">
            {@render badge(won === null ? null : won === 0)}
            {#if picks}{@render heroes(picks[0], false)}{:else}<span class="heroes muted">{drafts ? 'No draft' : '…'}</span>{/if}
            <span class="length">{d?.duration ? clock(d.duration) : won === null && drafts ? 'live' : ''}</span>
            {#if picks}{@render heroes(picks[1], false)}{:else}<span class="heroes"></span>{/if}
            {@render badge(won === null ? null : won === 1)}
            {#if bans && banned}
              <span></span>{@render heroes(banned[0], true)}<span class="muted length">bans</span>{@render heroes(banned[1], true)}<span></span>
            {/if}
          </a>
        </li>
      {/each}
    </ol>
    <footer>
      <span class="muted">Bans</span>
      <button class="link" onclick={() => (bans = !bans)} aria-pressed={bans}>{bans ? 'Hide' : 'Show'}</button>
    </footer>
  {/if}
</dialog>

<style>
  dialog {
    width: min(600px, calc(100vw - 32px));
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--raised);
    color: var(--text);
    box-shadow: 0 12px 40px rgb(0 0 0 / 0.45);
  }
  dialog:focus {
    outline: none; /* it takes the focus on opening, so Escape and Tab work without ringing the close button */
  }
  dialog::backdrop {
    background: rgb(0 0 0 / 0.45);
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px 0;
    font-size: 13px;
  }
  .close {
    border: 0;
    background: none;
    color: var(--text-2);
    font-size: 22px;
    line-height: 1;
    cursor: pointer;
  }
  .score {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 12px;
    padding: 8px 14px 14px;
    border-bottom: 1px solid var(--border);
  }
  .team {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    font-weight: 600;
  }
  .team.end {
    flex-direction: row-reverse;
    text-align: right;
  }
  .team img {
    object-fit: contain;
    flex: none;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .result {
    display: flex;
    flex-direction: column;
    align-items: center;
    font-size: 12px;
  }
  .result strong {
    font-size: 22px;
    font-variant-numeric: tabular-nums;
  }
  ol {
    list-style: none;
    margin: 0;
    padding: 6px;
  }
  li a {
    display: grid;
    grid-template-columns: 24px 1fr 56px 1fr 24px;
    align-items: center;
    row-gap: 4px;
    column-gap: 8px;
    padding: 6px 8px;
    border-radius: 6px;
    color: inherit;
    text-decoration: none;
  }
  li a:hover {
    background: var(--surface);
  }
  .heroes {
    display: flex;
    gap: 3px;
    min-width: 0;
  }
  li a > .heroes:nth-child(4),
  li a > .heroes:nth-child(9) {
    justify-content: flex-end;
  }
  .heroes img {
    flex: 0 1 auto;
    min-width: 0;
    height: auto; /* on a phone the five icons shrink to fit */
    border-radius: 3px;
  }
  .heroes.small img {
    filter: grayscale(0.7);
    opacity: 0.8;
  }
  .length {
    text-align: center;
    font-variant-numeric: tabular-nums;
    font-size: 13px;
    color: var(--text-2);
  }
  .badge {
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 700;
    color: var(--muted);
    background: var(--surface);
  }
  .badge.won {
    color: var(--page);
    background: var(--good);
  }
  .badge.lost {
    color: var(--page);
    background: var(--critical);
  }
  footer {
    display: flex;
    justify-content: center;
    gap: 8px;
    padding: 8px 14px 12px;
    border-top: 1px solid var(--border);
    font-size: 13px;
  }
  .link {
    border: 0;
    background: none;
    padding: 0;
    color: var(--series-1);
    cursor: pointer;
    font: inherit;
  }
</style>
