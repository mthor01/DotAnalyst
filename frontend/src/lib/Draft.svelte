<script lang="ts">
  import { heroIcon, heroName, heroPortrait } from './constants.svelte'

  type Turn = { hero_id: number; pick: boolean; radiant: boolean; n: number }
  /** captains: the draft as the game shows it: Radiant's heroes left, Dire's right, the turn numbers down the middle;
   *  otherwise only the bans and the order of the picks. notes: a word under each side's name. wide: a captains draft
   *  laid out left to right, Radiant's turns above Dire's, for a page that has the whole width for it. */
  let { draft, captains, notes, wide = false }: { draft: { hero_id: number; pick: boolean; radiant: boolean }[]; captains: boolean; notes?: [string, string]; wide?: boolean } = $props()

  const turns = $derived<Turn[]>(draft.map((d, i) => ({ ...d, n: i + 1 })))
  /** A turn shares its row with the next when that is the other side's turn of the same kind (both picks or both
   *  bans), as in the game. */
  const rows = $derived.by(() => {
    const out: Turn[][] = []
    for (let i = 0; i < turns.length; i++) {
      const [a, b] = [turns[i], turns[i + 1]]
      out.push(b && b.radiant !== a.radiant && b.pick === a.pick ? [a, turns[++i]] : [a])
    }
    return out
  })
  const what = (t: Turn) => `${t.n}. ${t.radiant ? 'Radiant' : 'Dire'} ${t.pick ? 'pick' : 'ban'}: ${heroName(t.hero_id)}`
</script>

{#if captains && wide}
  <!-- one column per row of the tall layout: a turn and, when the other side answers in kind, its answer -->
  <ol class="across" aria-label="Picks and bans in draft order" style="--turns: {rows.length}">
    <li class="side radiant">Radiant</li>
    <li class="side dire">Dire</li>
    {#each rows as row, c}
      {#each row as t}
        <li class="turn" class:dire={!t.radiant} class:ban={!t.pick} style="grid-column: {c + 2}">
          <img src={heroPortrait(t.hero_id)} alt={what(t)} title={what(t)} loading="lazy" />
          <span>{t.n}</span>
        </li>
      {/each}
    {/each}
  </ol>
{:else if captains}
  <div class="cm">
    <p class="sides">
      <b class="radiant">Radiant{#if notes}<small>{notes[0]}</small>{/if}</b>
      <b class="dire">Dire{#if notes}<small>{notes[1]}</small>{/if}</b>
    </p>
    <ol aria-label="Picks and bans in draft order">
      {#each rows as row}
        <li>
          {#each row as t, k}
            <img class="hero" class:dire={!t.radiant} class:ban={!t.pick} src={heroPortrait(t.hero_id)} alt={what(t)} title={what(t)} loading="lazy" />
            <span class="n" class:dire={!t.radiant} class:second={k === 1}>{t.n}</span>
          {/each}
        </li>
      {/each}
    </ol>
  </div>
{:else}
  <dl class="simple">
    <dt>Banned</dt>
    <dd>
      {#each turns.filter((t) => !t.pick) as t}
        <img class="icon" src={heroIcon(t.hero_id)} alt={heroName(t.hero_id)} title={heroName(t.hero_id)} width="32" height="32" loading="lazy" />
      {:else}
        <span class="muted">No bans</span>
      {/each}
    </dd>
    <dt>Picks</dt>
    <dd>
      <ol aria-label="Picks in order">
        {#each turns.filter((t) => t.pick) as t, i}
          <li class:dire={!t.radiant} title={`${i + 1}. ${t.radiant ? 'Radiant' : 'Dire'}: ${heroName(t.hero_id)}`}>
            <span class="n">{i + 1}</span>
            <img src={heroPortrait(t.hero_id)} alt={`${t.radiant ? 'Radiant' : 'Dire'}: ${heroName(t.hero_id)}`} loading="lazy" />
          </li>
        {/each}
      </ol>
    </dd>
  </dl>
{/if}

<style>
  /* columns: Radiant's heroes, the turn numbers, Dire's heroes; as tall as its grid row when it has one */
  .cm {
    --box: 60px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: fit-content;
    box-sizing: border-box;
    padding: 10px 12px;
    border-radius: 6px;
    background:
      linear-gradient(90deg, color-mix(in srgb, var(--radiant) 20%, transparent), transparent 40%),
      linear-gradient(270deg, color-mix(in srgb, var(--dire) 10%, transparent), transparent 40%),
      var(--surface);
  }
  .across {
    display: grid;
    grid-template-columns: auto repeat(var(--turns), minmax(52px, 1fr));
    gap: 6px 4px;
    overflow-x: auto;
    margin: 0;
    padding: 12px 14px;
    list-style: none;
    border-radius: 6px;
    background:
      linear-gradient(180deg, color-mix(in srgb, var(--radiant) 16%, transparent), transparent 50%),
      linear-gradient(0deg, color-mix(in srgb, var(--dire) 10%, transparent), transparent 50%),
      var(--surface);
  }
  .across .side {
    grid-column: 1;
    align-self: center;
    padding-right: 10px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.08em;
  }
  .across .radiant {
    color: var(--radiant);
  }
  .across .dire {
    grid-row: 2;
    color: var(--text-2);
  }
  /* Radiant's hero over its number, Dire's number over its hero, so the numbers meet in the middle */
  .turn {
    grid-row: 1;
    display: flex;
    flex-direction: column;
    justify-content: end;
    align-items: center;
    gap: 3px;
    font-size: 11px;
    color: var(--muted);
  }
  .turn.dire {
    grid-row: 2;
    flex-direction: column-reverse;
  }
  .turn img {
    width: 100%;
    aspect-ratio: 16 / 9;
    border: 1px solid var(--axis);
    border-radius: 3px;
    background: #000;
  }
  .turn.ban img {
    width: 75%;
    filter: grayscale(1);
    opacity: 0.55;
  }

  .sides,
  .cm li {
    display: grid;
    grid-template-columns: var(--box) 28px var(--box);
    column-gap: 10px;
  }
  .sides {
    margin: 0;
    font-size: 13px;
    line-height: 1.3;
    letter-spacing: 0.08em;
    text-align: center;
  }
  .sides b {
    display: flex;
    flex-direction: column;
  }
  .sides .radiant {
    color: var(--radiant);
    text-shadow: 0 0 8px color-mix(in srgb, var(--radiant) 60%, transparent);
  }
  .sides .dire {
    grid-column: 3;
    color: var(--text-2);
  }
  .sides small {
    font-weight: normal;
    letter-spacing: 0;
    color: var(--muted);
  }
  .cm ol {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 3px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .hero {
    grid-row: 1;
    grid-column: 1;
    justify-self: end;
    width: var(--box);
    aspect-ratio: 16 / 9;
    border: 1px solid var(--axis);
    border-radius: 3px;
    background: #000;
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.5);
  }
  .hero.dire {
    grid-column: 3;
    justify-self: start;
  }
  .hero.ban {
    width: calc(var(--box) * 0.75);
    align-self: center;
    filter: grayscale(1);
    opacity: 0.55;
  }
  .n {
    position: relative;
    grid-row: 1;
    grid-column: 2;
    justify-self: center;
    align-self: center;
    font-size: 11px;
    line-height: 1;
    color: var(--muted);
  }
  /* in a row of two, the first number sits at the top and the second at the bottom */
  li:has(.second) .n {
    align-self: start;
  }
  li .n.second {
    align-self: end;
  }
  /* a short line joins each number to its hero */
  .n::before {
    content: '';
    position: absolute;
    top: 50%;
    width: 12px;
    border-top: 1px solid var(--axis);
    right: calc(100% + 2px);
  }
  .n.dire::before {
    left: calc(100% + 2px);
    right: auto;
  }

  .simple {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 10px 16px;
    align-items: center;
    margin: 0;
  }
  .simple dt {
    color: var(--muted);
  }
  .simple dd {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin: 0;
  }
  .icon {
    border-radius: 3px;
    filter: grayscale(1);
    opacity: 0.7;
  }
  .simple ol {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .simple li {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    font-size: 11px;
    color: var(--muted);
  }
  /* the side as a bar under the hero */
  .simple li img {
    width: 64px;
    aspect-ratio: 16 / 9;
    border-radius: 3px;
    border-bottom: 3px solid var(--radiant);
    background: #000;
  }
  .simple li.dire img {
    border-bottom-color: var(--dire);
  }
</style>
