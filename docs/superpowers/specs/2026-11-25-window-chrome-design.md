# App window: title bar and scrollbar

**Why:** the desktop window looks cheap. Windows draws a white default title bar with the generic icon above the
dark page, and Edge draws its wide grey scrollbar with arrow buttons.

**Approaches:**
- **A. Native title bar, coloured (picked).** The bar is coloured through DWM, Windows' window compositor. Windows
  keeps snap layouts, edge resizing and the standard buttons.
- **B. A frameless window, with the page header as the title bar.** It was dropped: pywebview's frameless WinForms
  windows lose snap layouts and resize unreliably, and the buttons would have to be our own. That is more code and
  more ways to break, for 30 px of height.

**Design:**
- **Title bar:**
  - When the window is shown, `app.py` sets three DWM attributes on its handle: dark mode (20), caption colour (35)
    = `--page` `#151a21`, and caption text (36) = `--text` `#e4e7ea`.
  - The bar then reads as part of the page header below it.
  - Windows 10 ignores 35 and 36 and shows a plain dark bar.
  - Known limit: when Windows switches between light and dark apps, pywebview resets attribute 20. The caption stays
    coloured, but the button glyphs may go dark until the next start.
- **Icon:**
  - `packaging/dotanalyst.ico` is the D mark from `frontend/public/logo.png`, generated once and committed.
  - `webview.start(icon=...)` sets it on the window when run from source.
  - The PyInstaller spec gets `icon=` so the installed exe, shortcut and taskbar carry it. pywebview takes the
    window icon from the exe there.
  - This is the icon part of the installer design, done early.
- **Scrollbar:** in `app.css`, `scrollbar-width: thin` and `scrollbar-color: var(--axis) transparent` on every
  element. That gives a thin bar with no arrows, in the browser as well.

**Non-goals:** a custom title bar, the logo wordmark in the bar, scrollbar hover effects.

**Verification:**
- `npm run build`, with no Python logic to unit-test (only Windows calls).
- Start `python -m dotanalyst.app` without the poller and screenshot the window: bar colour, icon and scrollbar.
- `pytest` stays green.
