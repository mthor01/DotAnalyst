"""The desktop app: the server on a local port, shown in its own window. Run with: uv run python -m dotanalyst.app

Absolute imports, because PyInstaller runs this file as __main__."""
import os
import socket
import sys
import threading
from collections.abc import Callable
from pathlib import Path


def paint_title_bar(hwnd: int) -> None:
    """Windows 11 draws the title bar in the page's colour (#151a21, light text); Windows 10 ignores 35/36 and shows it
    plain dark. Run on `shown`: pywebview's constructor sets dark mode (20) from the Windows theme before that."""
    import ctypes

    for attr, value in ((20, 1), (35, 0x00211A15), (36, 0x00EAE7E4)):  # dark mode, caption, text; colours are 0x00BBGGRR
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(value)), 4)


def installed_settings(key: str = r"Software\DotAnalyst") -> dict[str, str]:
    """The setup's answers (DataDir, ReplayDir) under HKEY_CURRENT_USER; empty when it never wrote any."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return {name: value for name, value, _ in (winreg.EnumValue(k, i) for i in range(winreg.QueryInfoKey(k)[1]))}
    except FileNotFoundError:
        return {}


def home(settings: dict[str, str]) -> Path:
    """Where the installed app keeps its data, .env and log: the setup's data folder, else the user's app data."""
    return Path(settings.get("DataDir") or Path(os.environ["LOCALAPPDATA"]) / "DotAnalyst")


def run_at_login() -> bool:
    """The setup's "start with Windows": the Run value it writes. An app started there lives in the tray."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, "DotAnalyst")
        return True
    except FileNotFoundError:
        return False


def already_running() -> bool:
    """A DotAnalyst on 8765 answered and showed its window: never two pollers on one database."""
    import httpx

    try:
        return httpx.post("http://127.0.0.1:8765/api/desktop/show", timeout=2).json().get("app") == "DotAnalyst"
    except Exception:  # nothing there, or not us (0.1.0 has no such route)
        return False


def tray(icon_file: str | None, open_window: Callable[[], None], quit_app: Callable[[], None]):
    """The tray icon (left click or Open shows the window, Quit ends the app) on its own STA thread with its own
    message loop. Returns the NotifyIcon, for the balloon tip and to take it down at exit."""
    import clr  # pythonnet, already loaded by pywebview's WinForms

    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    from System import EventHandler
    from System.Drawing import Icon
    from System.Threading import ApartmentState, Thread, ThreadStart
    from System.Windows.Forms import Application, ContextMenuStrip, MouseButtons, MouseEventHandler, NotifyIcon

    made: list = []

    def run() -> None:
        icon = NotifyIcon()
        icon.Icon = Icon(icon_file) if icon_file else Icon.ExtractAssociatedIcon(sys.executable)
        icon.Text = icon.BalloonTipTitle = "DotAnalyst"
        icon.BalloonTipText = "Still running here and collecting your matches. Quit from this icon's menu."
        icon.ContextMenuStrip = ContextMenuStrip()
        icon.ContextMenuStrip.Items.Add("Open", None, EventHandler(lambda *_: open_window()))
        icon.ContextMenuStrip.Items.Add("Quit", None, EventHandler(lambda *_: quit_app()))
        icon.MouseClick += MouseEventHandler(lambda _, e: open_window() if e.Button == MouseButtons.Left else None)
        icon.Visible = True
        made.append(icon)
        Application.Run()

    thread = Thread(ThreadStart(run))
    thread.SetApartmentState(ApartmentState.STA)  # WinForms menus need it
    thread.IsBackground = True  # never keeps the process alive
    thread.Start()
    while not made and thread.IsAlive:
        threading.Event().wait(0.05)
    return made[0] if made else None


def main() -> None:
    if getattr(sys, "frozen", False):  # installed: the data, .env and logs live in the user's folders, not the program
        settings = installed_settings()
        folder = home(settings)
        folder.mkdir(parents=True, exist_ok=True)
        os.chdir(folder)
        sys.stdout = sys.stderr = open("dotanalyst.log", "a", buffering=1, encoding="utf-8")  # a windowed exe has none
        if already_running():
            return
        if "ReplayDir" in settings:  # "" = don't use the Dota client's replays
            from dotanalyst import load_env

            load_env()  # first, so a DOTA_REPLAY_DIR in .env still wins over the setup's answer
            os.environ.setdefault("DOTA_REPLAY_DIR", settings["ReplayDir"])

    import httpx
    import uvicorn
    import webview
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from dotanalyst import update
    from dotanalyst.api import app, engine  # after the chdir: it opens data/ and reads .env
    from dotanalyst.db import Hero
    from dotanalyst.steam import sync_constants

    pending: list[Path] = []
    in_tray = "--tray" in sys.argv or (getattr(sys, "frozen", False) and run_at_login())
    visible, quitting, back_to_tray = threading.Event(), threading.Event(), threading.Event()
    if "--tray" not in sys.argv:  # started at login: only the tray icon
        visible.set()

    def check(version: str) -> None:
        try:
            with httpx.Client() as client:
                if setup := update.download(client, version, Path("update")):
                    pending.append(setup)
        except Exception as error:
            print(f"update check failed: {error}")

    def updates(version: str) -> None:
        """Every start, and every 6 hours in the tray, where the app runs for days. A setup is installed when the
        window closes; in the tray that is right away while the window is hidden, and the setup starts it there again."""
        while True:
            check(version)
            if pending or not in_tray or quitting.wait(6 * 3600):
                break
        if pending and in_tray and not visible.is_set():
            back_to_tray.set()
            quit_app()

    def constants() -> None:  # every start, so heroes and items of a new Dota patch get their names
        try:
            with Session(engine) as session, httpx.Client() as client:
                sync_constants(session, client, os.environ.get("STEAM_API_KEY", ""))
        except Exception as error:
            print(f"hero and item names not refreshed: {error}")

    with Session(engine) as session:
        first_run = session.scalar(select(Hero.id).limit(1)) is None
    if first_run:
        constants()  # before the window, or its first page shows no hero pictures
    else:
        threading.Thread(target=constants, daemon=True).start()

    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 8765))  # a fixed port keeps the window's local storage (picked account) between starts
    except OSError:
        sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]})
    thread.start()
    while not server.started and thread.is_alive():
        threading.Event().wait(0.1)

    window = webview.create_window(
        "DotAnalyst", f"http://127.0.0.1:{port}/", width=1400, height=900, min_size=(900, 600), hidden=not visible.is_set()
    )
    window.events.shown += lambda: paint_title_bar(window.native.Handle.ToInt32())
    icon_file = Path(__file__).resolve().parent.parent / "packaging" / "dotanalyst.ico"  # from source; the exe has its own
    icon_file = str(icon_file) if icon_file.exists() else None
    tray_icon: list = []
    told = threading.Event()

    def open_window() -> None:
        visible.set()
        window.show()

    def quit_app() -> None:
        quitting.set()
        window.destroy()

    def closing() -> bool:  # in the tray, closing the window only hides it
        if quitting.is_set() or not in_tray:
            return True
        if pending:  # an update waits: install it now and come back to the tray
            back_to_tray.set()
            return True
        window.hide()
        visible.clear()
        if tray_icon and tray_icon[0] and not told.is_set():
            told.set()
            tray_icon[0].ShowBalloonTip(4000)
        return False

    def show() -> dict[str, str]:  # a second start asks the running app to show its window instead
        threading.Thread(target=open_window, daemon=True).start()
        return {"app": "DotAnalyst"}

    app.add_api_route("/api/desktop/show", show, methods=["POST"])
    app.router.routes.insert(0, app.router.routes.pop())  # ahead of the frontend's mount at /, which takes every path
    window.events.closing += closing

    def started() -> None:  # on its own thread once the GUI runs
        if in_tray:
            tray_icon.append(tray(icon_file, open_window, quit_app))
        if version := update.installed_version():
            updates(version)

    # private mode would forget the window's local storage at every close
    webview.start(started, private_mode=False, icon=icon_file)
    quitting.set()  # ends the 6-hourly wait
    if tray_icon and tray_icon[0]:
        tray_icon[0].Visible = False  # or a dead icon stays in the tray until the mouse passes over it
    server.should_exit = True
    thread.join()
    if pending:
        update.install(pending[0], tray=back_to_tray.is_set())


if __name__ == "__main__":
    main()
