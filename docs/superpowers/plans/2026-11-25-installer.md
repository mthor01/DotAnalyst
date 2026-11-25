# Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dark setup in the app's look, with the logo, that asks for the install folder, data folder, Dota replay folder and start with Windows; an app that reads those answers, lives in the tray, runs once, and an uninstall that asks before deleting data.

**Architecture:** Inno Setup writes the answers to `HKCU\Software\DotAnalyst`; `dotanalyst/app.py` reads them at start (frozen only). The tray is a WinForms NotifyIcon on its own thread. A second start finds the first through its HTTP port.

**Tech Stack:** Inno Setup 6.7 (Pascal script), Python 3.14, pywebview 6.2 (WinForms), pythonnet, winreg. No new dependencies.

**Spec:** docs/superpowers/specs/2026-11-25-installer-design.md

## Global Constraints

- No admin rights (`PrivilegesRequired=lowest`), everything under HKCU and the user's folders.
- Nothing in the data folder is deleted without an explicit Yes; a silent uninstall keeps it.
- A 0.1.0 install updates in place: same AppId, same default folders.
- Never two pollers on one database: one app instance.
- Running from source (`uv run python -m dotanalyst.app`, `uvicorn`) is unchanged: registry, tray and single instance only when frozen.
- No new dependencies.

## Review Focus

- A silent update (`/VERYSILENT`) must not rewrite the stored answers or the Run value with defaults.
- An empty replay folder answer ("don't use my replays") must turn the folder step off, not fall back to the Steam default.
- Closing the window in tray mode hides it; Quit from the tray must really end the server thread, or the exe never exits.
- The setup must close a running DotAnalyst (also one hidden in the tray) before it replaces files.
- A data folder chosen on a first install that already holds a database is used as is, never emptied.

---

### Task 1: Replay folder off switch

**Files:** Modify `dotanalyst/poll.py` (`replay_dir`, `folder_replays`, `steps`, `Setup.replay_dir`); Test `tests/test_desktop.py`

**Interfaces:** Produces `poll.replay_dir() -> Path | None` (None when `DOTA_REPLAY_DIR` is set to ""); `folder_replays(session, None) == []`; `steps()` folder row planned text `"off: no replay folder"`.

- [ ] Tests: `test_an_empty_replay_dir_turns_the_folder_off` (env "" → None, folder_replays → [], steps folder planned starts with "off"), `test_the_replay_dir_defaults_to_steam` (env unset → `poll.REPLAY_DIR`).
- [ ] Run, see them fail; implement; run; commit (stage only this hunk of poll.py: the user has an uncommitted hunk in `progress()`).

### Task 2: The app reads the setup's answers

**Files:** Modify `dotanalyst/app.py`; Test `tests/test_desktop.py`

**Interfaces:** Produces `installed_settings(key: str = r"Software\DotAnalyst") -> dict[str, str]` (empty dict when the key is missing); `home(settings) -> Path` = `DataDir` or `%LOCALAPPDATA%\DotAnalyst`.

- [ ] Tests: write values under a made-up `HKCU\Software\DotAnalystTest-<uuid>` key, read them back, delete the key; a missing key gives `{}`; `home({})` and `home({"DataDir": x})`.
- [ ] In `main()` (frozen): `home` from the settings; `os.environ.setdefault("DOTA_REPLAY_DIR", settings["ReplayDir"])` when present.
- [ ] Commit.

### Task 3: Tray, one instance, updates in the tray

**Files:** Modify `dotanalyst/app.py`, `dotanalyst/update.py`

**Interfaces:** `update.install(setup: Path, tray: bool = False)` adds `/TRAY`. Route `POST /api/desktop/show` added by app.py (frozen) → `{"app": "DotAnalyst"}` and shows the window.

- [ ] Single instance: before binding, POST to `127.0.0.1:8765/api/desktop/show` (timeout 2 s); a DotAnalyst answer → exit.
- [ ] Tray mode when frozen and (`--tray` in argv or the Run value exists): window created hidden with `--tray`; `closing` hides unless quitting, balloon once per run; NotifyIcon with Open / Quit on an STA thread.
- [ ] Updates in tray mode: check every 6 h; a pending setup installs when the window is hidden (or on next hide), with `/TRAY`.
- [ ] `test_update.py`: `install(..., tray=True)` passes `/TRAY`.
- [ ] Manual check from source with the frozen paths forced off; commit.

### Task 4: The setup

**Files:** Modify `packaging/dotanalyst.iss`; Create `packaging/setup-logo.png` (the logo, from `frontend/public/logo.png`)

- [ ] Look: `WizardStyle=modern dark includetitlebar hidebevels`, `WizardBackColor=#151a21`, `SetupIconFile=dotanalyst.ico`, no side/small images; logo.png in a `TBitmapImage` on the welcome page and in the top panel.
- [ ] Pages: install folder (`DisableDirPage=no`); data folder (`CreateInputDirPage`, only when no `DataDir` stored and the default holds no `data\dotanalyst.db`); replays (checkbox + folder, found via `HKCU\Software\Valve\Steam\SteamPath` and `libraryfolders.vdf`); tasks `desktopicon` (unchecked), `startup` (checked).
- [ ] `ssPostInstall`, not silent: write `DataDir`, `ReplayDir` ("" when unticked), Run value or delete it. `[Run]` `--tray` with Check on `/TRAY`.
- [ ] `PrepareToInstall` and uninstall: `taskkill /F /T /IM DotAnalyst.exe`. Uninstall: read `DataDir`, ask (default No; silent = No), delete the folder on Yes.
- [ ] Build with `build_noparser.ps1`, click through every page, screenshots; commit.

### Task 5: CI smoke test and docs

**Files:** Modify `.github/workflows/release.yml`, `IMPLEMENTATION.md`, `README.md`, the design doc (CI decision)

- [ ] After "Build the setup": silent install into `$env:RUNNER_TEMP\da`, assert the exe; put a file in `%LOCALAPPDATA%\DotAnalyst`; silent uninstall; assert the program folder is gone and the file stayed.
- [ ] Docs: replay folder rule, data folder, tray, one instance, updates. Commit.
