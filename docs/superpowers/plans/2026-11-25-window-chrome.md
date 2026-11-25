# Window chrome Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The desktop window gets a title bar in the page's colour, the D logo as its icon, and a thin dark scrollbar.

**Architecture:** `app.py` colours the native title bar through DWM once pywebview shows the window. The icon is a
committed `.ico` that is passed to `webview.start` from source and baked into the exe by PyInstaller. The scrollbar is
one CSS rule.

**Tech Stack:** pywebview 6.2.1 (WinForms + WebView2), ctypes/dwmapi, PyInstaller, Svelte/CSS, Pillow from system
Python (once, not a project dependency).

**Spec:** `docs/superpowers/specs/2026-11-25-window-chrome-design.md`

## Global Constraints

- No new dependencies. Pillow from system Python only generates the `.ico`, and the `.ico` is committed.
- Colours: caption `#151a21` → COLORREF `0x00211A15`; caption text `#e4e7ea` → `0x00EAE7E4`; scrollbar thumb `var(--axis)`.
- Running from source (`uvicorn dotanalyst.api:app`) is unchanged; the DWM code runs only in `dotanalyst.app`.
- Never touch the user's server on port 8000. Check with a poller-free server on another port.
- One commit per task, straight to main, staging files by name. Never stage the user's uncommitted files.

## Review Focus

1. **Windows 10 (build < 22000):** attributes 35/36 fail. DWM returns an error code, and that must not raise or crash
   the app. Check: the helper ignores the return value.
2. **Light Windows theme:** pywebview's constructor sets attribute 20 = 0. Ours must run after it (on `shown`), or the
   caption glyphs come out dark on dark.
3. **Frozen exe:** `packaging/dotanalyst.ico` is not bundled. The icon path must be passed only when the file exists,
   so pywebview falls back to the exe's own icon.
4. **Nested scroll containers** (tables, the filter panel) must get the thin bar too. `scrollbar-width` does not
   inherit, so the rule goes on `*`.

---

### Task 1: The icon

**Files:**
- Create: `packaging/dotanalyst.ico`
- Modify: `packaging/dotanalyst.spec:20`, `dotanalyst/app.py:68-69`

- [ ] **Step 1:** Generate the `.ico` with system `python`:
  - crop `frontend/public/logo.png` to columns 0–88 (the D mark);
  - trim it to its alpha bounding box, then pad it to a transparent square;
  - save as ICO with sizes 16, 24, 32, 48, 64, 128 and 256.
  - Look at the result at 32 and 256 px by saving PNG previews to the scratchpad.
- [ ] **Step 2:** In the spec, add `icon=ROOT + "\\packaging\\dotanalyst.ico"` to `EXE(...)`.
- [ ] **Step 3:** In `app.py`, set `ICON = Path(__file__).resolve().parent.parent / "packaging" / "dotanalyst.ico"`
  and call `webview.start(private_mode=False, icon=str(ICON) if ICON.exists() else None)`.
- [ ] **Step 4:** Commit: the `.ico`, the spec and `app.py`.

### Task 2: The coloured title bar

**Files:** Modify: `dotanalyst/app.py`

- [ ] **Step 1:** Add `def paint_title_bar(hwnd: int) -> None` to `app.py`. It sets these DWM attributes through
  `ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, byref(c_int(value)), 4)` and ignores the return codes:
  - 20 = 1
  - 35 = `0x00211A15`
  - 36 = `0x00EAE7E4`
- [ ] **Step 2:** Keep the window from `create_window`. Add the handler
  `window.events.shown += lambda: paint_title_bar(window.native.Handle.ToInt32())`.
- [ ] **Step 3:** Run the window from source without the poller:
  - Use a scratch script that sets `dotanalyst.api.app.router.lifespan_context` to a no-op, then calls
    `dotanalyst.app.main()`.
  - It uses port 8765, so check that nothing else is on it.
  - Screenshot the window with PowerShell `CopyFromScreen` on its bounds.
  - Expected: a `#151a21` bar, light title text, the D icon.
- [ ] **Step 4:** Commit `app.py`.

### Task 3: The scrollbar

**Files:** Modify: `frontend/src/app.css`

- [ ] **Step 1:** Add `* { scrollbar-width: thin; scrollbar-color: var(--axis) transparent; }`.
- [ ] **Step 2:** Run `npm run build` in `frontend/`. Expected: the build succeeds.
- [ ] **Step 3:** Check the Task 2 screenshot, or a headless Edge one of a long page: the thin bar, no arrows.
- [ ] **Step 4:** Run `uv run pytest -q` (expected: green), then commit `app.css` together with the spec and this plan.
