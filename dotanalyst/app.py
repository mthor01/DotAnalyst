"""The desktop app: the server on a local port, shown in its own window. Run with: uv run python -m dotanalyst.app

Absolute imports, because PyInstaller runs this file as __main__."""
import os
import socket
import sys
import threading
from pathlib import Path


def main() -> None:
    if getattr(sys, "frozen", False):  # installed: the data, .env and logs live in the user's app data, not the program
        home = Path(os.environ["LOCALAPPDATA"]) / "DotAnalyst"
        home.mkdir(parents=True, exist_ok=True)
        os.chdir(home)
        sys.stdout = sys.stderr = open("dotanalyst.log", "a", buffering=1, encoding="utf-8")  # a windowed exe has none

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

    def check(version: str) -> None:  # every start; a download the window outlasts is installed when it closes
        try:
            with httpx.Client() as client:
                if setup := update.download(client, version, Path("update")):
                    pending.append(setup)
        except Exception as error:
            print(f"update check failed: {error}")

    if version := update.installed_version():
        threading.Thread(target=check, args=(version,), daemon=True).start()

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

    webview.create_window("DotAnalyst", f"http://127.0.0.1:{port}/", width=1400, height=900, min_size=(900, 600))
    webview.start(private_mode=False)  # private mode would forget the window's local storage at every close
    server.should_exit = True
    thread.join()
    if pending:
        update.install(pending[0])


if __name__ == "__main__":
    main()
