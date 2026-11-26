<script lang="ts">
  import { get, post, type Account, type TournamentRow } from './lib/api'
  import { DESIGN, hiddenIds, prefs, remove, saveSettings, type Part } from './lib/settings.svelte'

  let { tab, accounts, onaccounts }: { tab: string; accounts: Account[]; onaccounts: () => void } = $props()
  const TABS = { general: 'General', fetching: 'Fetching', accounts: 'Accounts', data: 'Data', design: 'Design', about: 'About' }
  const shown = $derived(tab in TABS ? (tab as keyof typeof TABS) : 'general')
  const s = $derived(prefs.s)
  let status = $state('') // what the last change did, or why the server refused it

  // every change is kept at once; the server checks it and answers with all the values
  async function save(changes: Parameters<typeof saveSettings>[0], done = 'Saved.') {
    try {
      await saveSettings(changes)
      status = done
    } catch (e) {
      status = `Not saved: ${(e as Error).message}`
    }
  }
  const checked = (e: Event) => (e.currentTarget as HTMLInputElement).checked
  const value = (e: Event) => (e.currentTarget as HTMLInputElement | HTMLSelectElement).value

  // ---- General: the replay folder is Steam's own (null), none (''), or one chosen
  let folder = $state('')
  const folderMode = $derived(s?.replay_dir === null ? 'steam' : s?.replay_dir === '' ? 'off' : 'folder')
  let choosing = $state(false) // "This folder" picked, not saved yet
  async function open(what: 'data' | 'log') {
    try {
      await post('settings/open', { what })
    } catch (e) {
      status = (e as Error).message
    }
  }

  // ---- Fetching
  const CHECKS: [number, string][] = [[10, '10 seconds'], [60, 'minute'], [300, '5 minutes'], [900, '15 minutes'], [3600, 'hour']]
  let newKey = $state('')
  let altUser = $state('')
  let altPassword = $state('')
  $effect(() => {
    altUser = prefs.s?.alt_user ?? ''
  })
  async function saveKey(event: SubmitEvent) {
    event.preventDefault()
    try {
      prefs.s = await post('settings/steam-key', { key: newKey })
      ;[newKey, status] = ['', 'Steam key saved.']
    } catch (e) {
      status = `Not saved: ${(e as Error).message}`
    }
  }
  async function saveAlt(event: SubmitEvent) {
    event.preventDefault()
    await save({ alt_user: altUser.trim(), ...(altPassword && { alt_password: altPassword }) }, 'Second Steam account saved.')
    altPassword = ''
  }

  // ---- Accounts
  let leagues = $state<TournamentRow[]>([])
  const loadLeagues = () => get<TournamentRow[]>('leagues').then((found) => (leagues = found), (e) => (status = e.message))
  $effect(() => {
    if (shown === 'accounts') loadLeagues()
  })
  async function untrack(path: string, name: string, after: () => void) {
    if (!confirm(`Stop tracking ${name}? What is stored of it stays, and adding it again brings it back.`)) return
    try {
      await remove(path)
      status = `${name} is no longer tracked.`
      after()
    } catch (e) {
      status = (e as Error).message
    }
  }

  // ---- Data
  let parts = $state<{ name: string; bytes: number }[]>([])
  const loadStorage = () => get<typeof parts>('settings/storage').then((found) => (parts = found), (e) => (status = e.message))
  const size = (bytes: number) =>
    bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : bytes >= 1e6 ? `${(bytes / 1e6).toFixed(0)} MB` : `${(bytes / 1e3).toFixed(0)} KB`
  let days = $state(180)
  async function removeOutput() {
    if (!confirm(`Delete the parser output of every match older than ${days} days? Their stats stay, but they can no longer be recomputed or played back on the map, and their replays are not downloaded again.`)) return
    try {
      const done = await post<{ files: number; bytes: number }>('settings/remove-parser-output', { days })
      status = `Deleted ${done.files} files, ${size(done.bytes)}.`
      loadStorage()
    } catch (e) {
      status = (e as Error).message
    }
  }
  type Recompute = { running: boolean; done: number; total: number; problems: number; finished: number | null }
  let recompute = $state<Recompute | null>(null)
  $effect(() => {
    if (shown !== 'data') return
    loadStorage()
    get<Recompute>('settings/recompute').then((r) => (recompute = r), () => {})
  })
  // while one runs, its count is asked for every 2 seconds
  $effect(() => {
    if (shown !== 'data' || !recompute?.running) return
    const timer = setInterval(() => get<Recompute>('settings/recompute').then((r) => (recompute = r), () => {}), 2000)
    return () => clearInterval(timer)
  })
  async function startRecompute() {
    recompute = await post<Recompute>('settings/recompute')
  }

  // ---- Design: a part is shown unless its id is in the hidden list; a hidden page or tab hides what is under it
  function toggle(id: string) {
    const ids = hiddenIds()
    save({ hidden: (ids.includes(id) ? ids.filter((h) => h !== id) : [...ids, id]).join(',') })
  }

  // ---- About
  let newest = $state<{ current: string | null; newest: string; newer: boolean } | null>(null)
  let asking = $state(false)
  async function checkUpdate() {
    asking = true
    try {
      newest = await get('settings/update')
    } catch (e) {
      status = (e as Error).message
    }
    asking = false
  }
</script>

{#snippet design(list: Part[], under: boolean)}
  <ul>
    {#each list as p (p.id)}
      {@const off = hiddenIds().includes(p.id)}
      <li>
        {#if p.group}
          <h3>{p.label}</h3>
        {:else}
          <label class:dim={under}><input type="checkbox" checked={!off} disabled={under} onchange={() => toggle(p.id)} /> {p.label}</label>
        {/if}
        {#if p.parts}{@render design(p.parts, under || off)}{/if}
      </li>
    {/each}
  </ul>
{/snippet}

<h2>Settings</h2>
<div class="choice tabs" role="group" aria-label="Part of the settings">
  {#each Object.entries(TABS) as [id, title]}
    <button aria-pressed={shown === id} onclick={() => ((status = ''), (location.hash = `settings/${id}`))}>{title}</button>
  {/each}
</div>
<p class="muted status" role="status">{status}</p>

{#if !s}
  <p class="muted">Loading…</p>
{:else if shown === 'general'}
  <section class="card">
    <label class="row">
      <span>Main profile<small>The profile the site opens with, and the first in the player comparison</small></span>
      <select value={s.main_account} onchange={(e) => save({ main_account: value(e) })}>
        <option value="">None: the one picked last</option>
        {#each accounts as a (a.account_id)}<option value={String(a.account_id)}>{a.label ?? a.account_id}</option>{/each}
      </select>
    </label>
    <label class="row">
      <span>Automatic updates<small>Look for a new version at every start and every 6 hours in the tray, and install it when the window closes{s.start_with_windows === null ? '. Only the installed program updates itself' : ''}</small></span>
      <input type="checkbox" checked={s.auto_update} onchange={(e) => save({ auto_update: checked(e) })} />
    </label>
    <label class="row">
      <span>Start with Windows<small>{s.start_with_windows === null ? 'Only for the installed program' : 'In the tray, fetching in the background'}</small></span>
      <input type="checkbox" checked={!!s.start_with_windows} disabled={s.start_with_windows === null} onchange={(e) => save({ start_with_windows: checked(e) })} />
    </label>
    <div class="row">
      <span>Dota replay folder<small>Replays you downloaded in the Dota client are read from here instead of fetched again</small></span>
      <span class="stack">
        <select aria-label="Dota replay folder" value={choosing ? 'folder' : folderMode} onchange={(e) => {
          const mode = value(e)
          choosing = mode === 'folder'
          folder = s.replay_dir ?? ''
          if (mode !== 'folder') save({ replay_dir: mode === 'steam' ? null : '' })
        }}>
          <option value="steam">Steam's own folder</option>
          <option value="off">None</option>
          <option value="folder">This folder…</option>
        </select>
        {#if choosing || folderMode === 'folder'}
          <form class="inline" onsubmit={(e) => { e.preventDefault(); save({ replay_dir: folder.trim() }).then(() => (choosing = false)) }}>
            <input bind:value={folder} required placeholder={s.replay_dir || 'D:\\Steam\\...\\replays'} aria-label="Replay folder" size="34" />
            <button class="action">Save</button>
          </form>
        {/if}
      </span>
    </div>
    <div class="row">
      <span>Data folder<small>The database, the parser output, .env and the log. The setup chooses it; to move it, reinstall</small></span>
      <span class="stack"><code>{s.data_folder}</code><button class="action" onclick={() => open('data')}>Open</button></span>
    </div>
  </section>
{:else if shown === 'fetching'}
  <section class="card">
    <label class="row">
      <span>Pause fetching<small>No new matches and no replays until it is turned off again; Check for new games still works</small></span>
      <input type="checkbox" checked={s.paused} onchange={(e) => save({ paused: checked(e) })} />
    </label>
    <label class="row">
      <span>Look for new games every<small>How often Steam is asked for new matches of the profiles and new games of the tournaments</small></span>
      <select value={s.check_seconds} onchange={(e) => save({ check_seconds: Number(value(e)) })}>
        {#each CHECKS.some(([v]) => v === s.check_seconds) ? CHECKS : [...CHECKS, [s.check_seconds, `${s.check_seconds} seconds`] as [number, string]] as [v, name]}
          <option value={v}>{name}</option>
        {/each}
      </select>
    </label>
    <label class="row">
      <span>Download replays of the last<small>Days, at most 100: Valve keeps replays about that long</small></span>
      <span class="stack"><input type="number" min="1" max="100" value={s.max_age_days} onchange={(e) => save({ max_age_days: Number(value(e)) })} /> days</span>
    </label>
    <label class="row">
      <span>Download speed cap<small>For all replay downloads together; 0 for no cap</small></span>
      <span class="stack"><input type="number" min="0" step="0.5" value={s.download_limit / 1024} onchange={(e) => save({ download_limit: Math.round(Number(value(e)) * 1024) })} /> MB/s</span>
    </label>
  </section>
  <section class="card">
    <form class="row" onsubmit={saveKey}>
      <span>Steam Web API key<small>{s.steam_key ? 'Saved. Enter a new one to replace it.' : 'Missing: no new matches are fetched without one.'} Get one at <a href="https://steamcommunity.com/dev/apikey" target="_blank" rel="noreferrer">steamcommunity.com/dev/apikey</a></small></span>
      <span class="stack">
        <input bind:value={newKey} required aria-label="Steam Web API key" placeholder={s.steam_key ? '•••• saved' : 'Steam Web API key'} size="34" />
        <button class="action">Save</button>
      </span>
    </form>
    <form class="row" onsubmit={saveAlt}>
      <span>Second Steam account<small>Asks Valve for replay ids, so fewer replays wait on OpenDota. Use an account of its own, not yours. Its first login needs the Steam Guard code typed once by hand: <code>node --env-file=.env steam/salts.mjs</code> in the program's folder</small></span>
      <span class="stack">
        <input bind:value={altUser} aria-label="Steam account name" placeholder="account name" autocomplete="off" />
        <input bind:value={altPassword} type="password" aria-label="Steam password" placeholder={s.alt_password ? '•••• saved' : 'password'} autocomplete="new-password" />
        <button class="action">Save</button>
      </span>
    </form>
  </section>
{:else if shown === 'accounts'}
  <h3>Tracked profiles</h3>
  <p class="muted">Add one with Add profile at the top.</p>
  <ul class="card list">
    {#each accounts as a (a.account_id)}
      {@const name = a.label ?? String(a.account_id)}
      {@const main = s.main_account === String(a.account_id)}
      <li>
        <span class="pic">{#if a.avatar}<img src={a.avatar} alt="" width="32" height="32" />{/if}</span>
        <span class="who"><b>{name}</b><small class="muted">{a.account_id}</small></span>
        {#if main}<span class="badge">Main profile</span>{:else}<button class="action" onclick={() => save({ main_account: String(a.account_id) }, `${name} is the main profile.`)}>Make main</button>{/if}
        <button class="action" onclick={() => untrack(`accounts/${a.account_id}`, name, onaccounts)}>Remove</button>
      </li>
    {:else}
      <li class="muted">No tracked profiles.</li>
    {/each}
  </ul>
  <h3>Tracked tournaments</h3>
  <p class="muted">Add one on the <a href="#tournaments">Tournaments</a> page. Taken off, its stored games stay, but no new ones and no more replays are fetched.</p>
  <ul class="card list">
    {#each leagues as l (l.league_id)}
      <li>
        <span class="who"><b>{l.name}</b><small class="muted">{l.games} stored games</small></span>
        <button class="action" onclick={() => untrack(`leagues/${l.league_id}`, l.name, loadLeagues)}>Remove</button>
      </li>
    {:else}
      <li class="muted">No tracked tournaments.</li>
    {/each}
  </ul>
{:else if shown === 'data'}
  <section class="card">
    <h3>Space used</h3>
    <table class="sizes">
      <tbody>
        {#each parts as p (p.name)}<tr><td>{p.name}</td><td class="num">{size(p.bytes)}</td></tr>{/each}
      </tbody>
      <tfoot><tr><td>All</td><td class="num">{size(parts.reduce((n, p) => n + p.bytes, 0))}</td></tr></tfoot>
    </table>
  </section>
  <section class="card">
    <div class="row">
      <span>Delete old parser output<small>The parser output is most of the space. Without it a match keeps its stats, but cannot be recomputed or played back on the map, and its replay is not downloaded again</small></span>
      <span class="stack">older than <input type="number" min="1" bind:value={days} aria-label="Days" /> days <button class="action" onclick={removeOutput}>Delete</button></span>
    </div>
    <div class="row">
      <span>Recompute stats<small>Rebuilds every parsed match's stats from its parser output, as after an update that changed how a stat is worked out. Takes a while; the site stays usable</small></span>
      <span class="stack">
        {#if recompute?.running}
          <span>{recompute.done} of {recompute.total} matches…</span>
        {:else}
          {#if recompute?.finished}<span class="muted">Last run: {recompute.done} matches{recompute.problems ? `, ${recompute.problems} without parser output` : ''}</span>{/if}
          <button class="action" onclick={startRecompute}>Recompute</button>
        {/if}
      </span>
    </div>
  </section>
{:else if shown === 'design'}
  <p class="muted">Untick what you do not want to see: a page, a tab, a block in it, or a filter. A hidden filter no longer narrows the pages.</p>
  <p><button class="action" disabled={!hiddenIds().length} onclick={() => save({ hidden: '' })}>Show everything</button></p>
  <div class="card tree">{@render design(DESIGN, false)}</div>
{:else}
  <section class="card">
    <div class="row">
      <span>Version<small>{s.start_with_windows === null ? 'Run from source: it does not update itself' : 'The installed program'}</small></span>
      <span class="stack">
        {#if newest}
          <span>{newest.current ?? 'source'}; newest release {newest.newest}{newest.newer ? (s.auto_update ? ', installed when the window closes after the next check' : ', automatic updates are off') : ''}</span>
        {/if}
        <button class="action" onclick={checkUpdate} disabled={asking}>{asking ? 'Asking GitHub…' : 'Check for updates'}</button>
      </span>
    </div>
    <div class="row">
      <span>Log<small>What the program did, for a bug report</small></span>
      <button class="action" onclick={() => open('log')}>Open the log</button>
    </div>
    <div class="row">
      <span>Source and releases</span>
      <a href="https://github.com/mthor01/DotAnalyst" target="_blank" rel="noreferrer">github.com/mthor01/DotAnalyst</a>
    </div>
  </section>
{/if}

<style>
  .tabs {
    margin-bottom: 6px;
  }
  .status {
    min-height: 1.4em;
    margin: 4px 0 10px;
  }
  .card {
    max-width: 980px;
    margin: 0 0 14px;
    padding: 4px 18px;
  }
  /* a setting: what it is and what it does on the left, its control on the right */
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px 24px;
    padding: 14px 0;
    border-top: 1px solid var(--grid);
    color: var(--text); /* a label row too, not the muted label of the filter panel */
  }
  .card > .row:first-child {
    border-top: 0;
  }
  .row > span:first-child {
    display: grid;
    flex: 1 1 320px;
    gap: 2px;
    font-weight: 600;
  }
  small {
    font-size: 13px;
    font-weight: 400;
    color: var(--muted);
  }
  .stack,
  .inline {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  input[type='number'] {
    width: 6em;
  }
  input[type='checkbox'] {
    width: 18px;
    height: 18px;
    accent-color: var(--series-1);
  }
  code {
    font-size: 13px;
    color: var(--text-2);
    word-break: break-all;
  }
  h3 {
    margin: 18px 0 4px;
  }
  .card h3 {
    margin: 12px 0 6px;
  }
  .list {
    padding: 0;
    list-style: none;
  }
  .list li {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 18px;
    border-top: 1px solid var(--grid);
  }
  .list li:first-child {
    border-top: 0;
  }
  .pic {
    width: 32px;
    height: 32px;
    border-radius: 4px;
    overflow: hidden;
    background: var(--raised);
  }
  .pic img {
    display: block;
  }
  .who {
    display: grid;
    flex: 1;
    min-width: 0;
  }
  .badge {
    padding: 2px 10px;
    border: 1px solid var(--border);
    border-radius: 10px;
    font-size: 12px;
    color: var(--text-2);
  }
  .sizes {
    width: auto;
    min-width: 320px;
    margin-bottom: 10px;
  }
  .sizes tfoot td {
    font-weight: 700;
    border-top: 1px solid var(--border);
  }
  .tree {
    padding: 12px 18px;
  }
  .tree ul {
    margin: 0;
    padding-left: 22px;
    list-style: none;
  }
  .tree > ul {
    padding-left: 0;
    columns: 2 320px;
    column-gap: 32px;
  }
  .tree > ul > li {
    break-inside: avoid;
    margin-bottom: 12px;
  }
  .tree label {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
    cursor: pointer;
  }
  .tree > ul > li > label,
  .tree h3 {
    margin: 0;
    font-weight: 700;
  }
  .dim {
    opacity: 0.45;
  }
</style>
