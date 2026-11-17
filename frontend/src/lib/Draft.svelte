<script lang="ts">
  import { heroIcon, heroName, heroPortrait } from './constants.svelte'

  type Turn = { hero_id: number; pick: boolean; radiant: boolean; n: number }
  /** captains: the draft as the game shows it, turned on its side: Radiant's row on top, Dire's below, the turn
   *  numbers between them; otherwise only the bans and the order of the picks. notes: a word under each side's name. */
  let { draft, captains, notes }: { draft: { hero_id: number; pick: boolean; radiant: boolean }[]; captains: boolean; notes?: [string, string] } = $props()

  const turns = $derived<Turn[]>(draft.map((d, i) => ({ ...d, n: i + 1 })))
  /** A turn shares its column with the next when that is the other side's turn of the same kind (both picks or both
   *  bans), as in the game. */
  const columns = $derived.by(() => {
    const out: Turn[][] = []
    for (let i = 0; i < turns.length; i++) {
      const [a, b] = [turns[i], turns[i + 1]]
      out.push(b && b.radiant !== a.radiant && b.pick === a.pick ? [a, turns[++i]] : [a])
    }
    return out
  })
  const what = (t: Turn) => `${t.n}. ${t.radiant ? 'Radiant' : 'Dire'} ${t.pick ? 'pick' : 'ban'}: ${heroName(t.hero_id)}`
</script>

{#if captains}
  <div class="cm">
    <p class="sides">
      <b class="radiant">Radiant{#if notes}<small>{notes[0]}</small>{/if}</b>
      <b class="dire">Dire{#if notes}<small>{notes[1]}</small>{/if}</b>
    </p>
    <ol aria-label="Picks and bans in draft order">
      {#each columns as column}
        <li>
          {#each column as t, k}
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
  /* rows: Radiant's heroes, the numbers, Dire's heroes */
  .cm {
    --box: 64px;
    display: flex;
    gap: 12px;
    width: fit-content;
    max-width: 100%;
    box-sizing: border-box;
    padding: 10px 12px;
    overflow-x: auto;
    border-radius: 6px;
    background:
      linear-gradient(180deg, color-mix(in srgb, var(--radiant) 20%, transparent), transparent 40%),
      linear-gradient(0deg, color-mix(in srgb, var(--dire) 10%, transparent), transparent 40%),
      var(--surface);
  }
  .sides,
  .cm li {
    display: grid;
    grid-template-rows: calc(var(--box) * 9 / 16) 22px calc(var(--box) * 9 / 16);
  }
  .sides {
    margin: 0;
    font-size: 13px;
    line-height: 1.3;
    letter-spacing: 0.08em;
  }
  .sides b {
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .sides .radiant {
    color: var(--radiant);
    text-shadow: 0 0 8px color-mix(in srgb, var(--radiant) 60%, transparent);
  }
  .sides .dire {
    grid-row: 3;
    color: var(--text-2);
  }
  .sides small {
    font-weight: normal;
    letter-spacing: 0;
    color: var(--muted);
  }
  .cm ol {
    display: flex;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .hero {
    grid-row: 1;
    grid-column: 1;
    justify-self: center;
    width: var(--box);
    aspect-ratio: 16 / 9;
    border: 1px solid var(--axis);
    border-radius: 3px;
    background: #000;
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.5);
  }
  .hero.dire {
    grid-row: 3;
  }
  .hero.ban {
    width: calc(var(--box) * 0.75);
    align-self: center;
    filter: grayscale(1);
    opacity: 0.55;
  }
  .n {
    position: relative;
    grid-row: 2;
    grid-column: 1;
    justify-self: center;
    align-self: center;
    font-size: 11px;
    line-height: 1;
    color: var(--muted);
  }
  /* in a column of two, the first number sits left and the second right */
  li:has(.second) .n {
    justify-self: start;
    margin-left: 8px;
  }
  li .n.second {
    justify-self: end;
    margin: 0 8px 0 0;
  }
  /* a short line joins each number to its hero */
  .n::before {
    content: '';
    position: absolute;
    left: 50%;
    height: 6px;
    border-left: 1px solid var(--axis);
    bottom: calc(100% + 1px);
  }
  .n.dire::before {
    top: calc(100% + 1px);
    bottom: auto;
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
