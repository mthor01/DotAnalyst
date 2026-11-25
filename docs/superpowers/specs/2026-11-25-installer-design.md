# Installer redesign, app icon and tray

## Why

The setup (`packaging/dotanalyst.iss`) is Inno Setup's plain grey default, and the installed program shows PyInstaller's
standard icon everywhere. The user wants the setup to look like the app and carry the DotAnalyst logo with its wordmark,
the logo to be the program's icon, and the setup to ask a few things that today are fixed:

- whether to use the replays Dota has already downloaded (the user's must-have),
- where to install the program,
- where to keep the data,
- whether DotAnalyst starts with Windows,
- on uninstall, whether to delete the data.

The user turned down a Steam API key field and a "players to follow" page (the app asks for both itself) and a
desktop shortcut ticked by default.

## Goals

1. A dark setup in the app's colours, with the logo (icon + "DotAnalyst" wordmark) in a band at the top of every page.
2. The logo as the icon of `DotAnalyst.exe`, the setup, the Start menu and desktop shortcuts, the taskbar, the window,
   the tray and the "Installed apps" list.
3. Pages, in this order: install folder → data folder (first install only) → Dota replays → extra tasks (desktop
   shortcut, start with Windows) → install → finish with "Start DotAnalyst".
4. Start with Windows: DotAnalyst starts at login as a tray icon, without a window, and keeps fetching.
5. The uninstaller asks whether to delete the data folder too.

## Non-goals

- Changing any choice inside the app (start with Windows, replay folder, data folder): run the setup again for the
  first two. Moving the data folder later is out entirely.
- Asking for the Steam API key or players in the setup.
- The Archivo font in the setup (it uses Windows' own font).
- A window icon when run from source (`python -m dotanalyst.app`).
- Signing the setup.

## Anti-goals: it fails if

- the setup asks for admin rights (the silent in-app update depends on it not doing so);
- a setup or uninstall deletes or moves data without the user saying yes;
- an existing 0.1.0 install changes behaviour when it updates silently: no data folder or replay folder recorded means
  today's defaults, not "off";
- two DotAnalyst processes poll the same database (likely once one hides in the tray and the user starts it again);
- running from source (`uvicorn dotanalyst.api:app`, `python -m dotanalyst.app`) behaves differently from now.

## Constraints

- No new dependencies. Pillow (system Python) may make the `.ico` once; the `.ico` is committed. The tray uses
  WinForms through pythonnet, which pywebview's WinForms backend already bundles.
- Inno Setup 6.6+ (local install and CI's `choco install innosetup`): `WizardStyle` dark, image files, Pascal `[Code]`.
- `AppId` stays the same so new setups upgrade old installs.
- The repo is public: nothing committed names a real player; registry and file paths in tests are made up.
- Tests never touch the live APIs; the installer script and the tray UI get no unit tests (see Verification).

## Approaches

For start with Windows (the only choice that changed how much gets built):

- **A. Tray icon (picked by the user).** At login it starts hidden as an icon by the clock and fetches in the
  background. Clicking the icon opens the window, and closing the window hides it to the tray. Quit really exits.
  About 60 lines on WinForms' `NotifyIcon`, with no new library.
- **B. Minimized window.** About 5 lines, but closing the window quits as today, so fetching stops until the next
  login, which defeats the purpose.

There were no real alternatives for the rest. The setup is already Inno Setup, and Inno's own dark style, image files
and `[Code]` pages cover the design. Answers go in the registry, where Inno reads and writes natively and Python reads
with the standard `winreg`.

## Design

### The icon

- `packaging/dotanalyst.ico`, made from the "D" mark of `frontend/public/logo.png`:
  - It takes columns 0–88 of the 418×64 file, has a transparent background and is padded to a square.
  - It holds sizes 16, 24, 32, 48 and 64, plus 128 and 256 scaled up.
- It is used by:
  - `dotanalyst.spec` (`EXE(icon=...)`), which sets the exe, shortcut, taskbar, window and tray icon;
  - `SetupIconFile`, which sets the setup's own icon;
  - `UninstallDisplayIcon`, which already points at the exe.
- Known limit: the largest original is 64 px tall, so the big sizes look soft. Redo the `.ico` from a larger original
  when there is one.

### The setup's look

- **Style:** Inno's dark wizard style, with the app's colours:
  - window `#151a21`, top band and fields `#1e252e`
  - text `#e4e7ea`, secondary text `#b6bec8`
  - accent (focus, progress) `#4d95ea`
- **Top band:** `#1e252e`, with `frontend/public/logo.png` (icon + white wordmark) on the left at its native 64 px
  height or smaller. It replaces Inno's small top-right image.
- **Page title and description:** they move below the band as the page's heading in `#e4e7ea`, with a smaller line in
  `#b6bec8`, so the wordmark has the band to itself.
- No welcome page (Inno's default). The first page is the install folder.

```
┌──────────────────────────────────────────────────┐
│ ▲ DotAnalyst                                     │  band #1e252e, logo + wordmark
├──────────────────────────────────────────────────┤
│ Dota replays                                     │  page heading
│ DotAnalyst can read the replays Dota downloaded  │  description, #b6bec8
│ instead of downloading them again.               │
│                                                  │
│ [x] Use the replays Dota already downloaded      │
│ [D:\SteamLibrary\…\game\dota\replays] [Browse…]  │
│                                                  │
│                        [Back] [Next] [Cancel]    │
└──────────────────────────────────────────────────┘
```

### The pages and where the answers go

The answers go under `HKCU\Software\DotAnalyst`. The uninstaller removes the key.

| Page | Shown | Default | Stored |
|---|---|---|---|
| Install folder | every interactive install (`DisableDirPage=no`) | `{localappdata}\Programs\DotAnalyst`, or the previous install's | Inno's own |
| Data folder | only when `DataDir` is not stored yet and no data exists in the default folder | `%LOCALAPPDATA%\DotAnalyst` | `DataDir` |
| Dota replays | every interactive install | the previous answer; on a first install, ticked with the detected folder, or unticked when none is found | `ReplayDir`: the folder, or `""` when unticked |
| Extra tasks | every interactive install | desktop shortcut off, start with Windows off; then the previous choices (Inno remembers tasks) | Inno's own, plus the Run value below |

Data folder: the page is skipped when the default folder already has data, because a 0.1.0 install has data there with
no `DataDir` recorded.

**Finding Dota's replay folder:**

1. Read `SteamPath` from `HKCU\Software\Valve\Steam`.
2. Take the libraries it lists: Steam's own folder, plus every `"path"` line in
   `<SteamPath>\steamapps\libraryfolders.vdf`.
3. Use the first library where `steamapps\common\dota 2 beta\game\dota\replays` exists.

If none is found, the box is unticked, the field is empty and a line says Dota 2 wasn't found. The user can still tick
the box and browse. When the box is ticked, the folder must exist before **Next** goes on.

**Start with Windows:**

- When ticked, the setup writes the Run value `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` → `DotAnalyst` =
  `"{app}\DotAnalyst.exe" --tray`.
- When unticked, it deletes that value, so unticking on a reinstall turns it off.
- The uninstaller deletes it.

**Silent updates** (`/VERYSILENT` from the app) show no pages. They keep every stored answer and the remembered tasks,
and never write `DataDir` or `ReplayDir`.

### The app reading the answers

When frozen, `app.py` reads `HKCU\Software\DotAnalyst` with `winreg` before anything else:

- **`DataDir`:** when set, it replaces `%LOCALAPPDATA%\DotAnalyst` as the folder the app `chdir`s into. The database,
  `.env`, logs and downloaded updates all go there.
- **`ReplayDir`:** when present (even `""`), it goes into `os.environ.setdefault("DOTA_REPLAY_DIR", value)`. A
  `DOTA_REPLAY_DIR` the user set in Windows still wins.

`poll.replay_dir()` treats an empty `DOTA_REPLAY_DIR` as off:

- It returns `None` when the variable is set but empty.
- `folder_replays` returns `[]` for `None`, and the queue's `steps` shows no folder step.
- With the variable unset, it returns today's default path, so running from source and old installs are unchanged.

### Tray (start with Windows)

The installed app starts in tray mode when started with `--tray`, or when the Run value exists. Run from source, it
never does. With neither, the app behaves
exactly as today: closing the window quits.

In tray mode:

- **Starting:** with `--tray` the window is created hidden, and only the tray icon shows.
- **The tray icon:**
  - The tooltip is "DotAnalyst".
  - A click opens and raises the window.
  - The right-click menu has **Open DotAnalyst** and **Quit**.
- **Closing the window** hides it instead of quitting. The first time per run, a tray notification says "DotAnalyst
  keeps fetching in the background. Quit from this icon."
- **Quit** closes the window for real. Then everything goes on as today when the window closes: the server stops and a
  pending update installs.

**Updates.** In tray mode the update check repeats every 6 hours, besides at start, so a parser update for a new Dota
patch reaches a PC that is never restarted.

- A downloaded update installs at once if the window is hidden. If the window is open, it installs when the window is
  next hidden or closed.
- The app exits itself first, then runs the setup with an extra `/TRAY` switch. The setup's `[Run]` entry then starts
  `DotAnalyst.exe --tray` again, even though it runs silently.
- An update installed after **Quit** still does not restart the app (`skipifsilent`, as today).

### One instance

A second start, for example from the Start menu while the first instance sits in the tray, must not start a second
server and poller.

- The second process asks the first, over its fixed local port 8765, to show its window, then exits.
- When nothing answers there as DotAnalyst, it starts normally (the port may be taken by something else, as today).
- The mechanism is the builder's call: a tiny endpoint or a named mutex plus the endpoint.

### Uninstall

The uninstaller first closes a DotAnalyst that is still running, which may be hidden in the tray. Its files would
otherwise be locked.

After the files are removed, an interactive uninstall asks:

> Also delete your DotAnalyst data (database, settings, downloaded replays) in `<DataDir>`?

- The default button is **No**.
- The uninstaller says **No** for itself when it runs silently.
- It never touches Dota's own replay folder.
- The data folder is read from `DataDir`, with the default when `DataDir` is missing.

## Verification

- **pytest:**
  - `replay_dir()` returns the default path when the variable is unset, `None` when it is empty, and the path when it
    is set.
  - `folder_replays` with `None` returns `[]`.
  - The registry-to-settings step in `app.py`, if it is split into a small function, is tested against a made-up
    key under HKCU.
- **Build:** `packaging\build.ps1` builds the setup, and CI must stay green.
- **By hand (no unit tests):**
  - Run the setup through every page, check the look against the sketch, and take screenshots.
  - Install into a scratch folder.
  - Start with `--tray`; hide, reopen and Quit.
  - Start a second instance.
  - Uninstall, once answering No and once Yes, with a scratch data folder.
  - Check that a silent install over the result keeps the answers.
- **Docs:**
  - `IMPLEMENTATION.md`: the replay folder rule (registry, off switch), the data folder, and tray, update and
    one-instance behaviour.
  - `README.md` Install section: the setup's options and the tray.

## Left to the builder

- How the band and the heading are drawn: Inno style and image settings, or `[Code]` moving the stock controls.
- Inno's exact colour syntax, and which controls need `[Code]` to take the colours.
- The Pascal for the replay detection and the checkbox on an input-folder page.
- The single-instance mechanism.
- Threading of the `NotifyIcon` next to pywebview's WinForms loop: closing is cancelled from pywebview's `closing`
  event.
- Whether the `.ico` generator is kept as a script or only its command is recorded in the commit message.
