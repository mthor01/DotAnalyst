"""The installed app's update: at every start it asks GitHub for the newest release (.github/workflows/release.yml
makes one when odota/parser or the app changed, e.g. after a Dota patch). A newer setup is downloaded in the
background and run silently once the window is closed, so the next start is the new version."""
import hashlib
import subprocess
import sys
from pathlib import Path

import httpx

RELEASES = "https://api.github.com/repos/mthor01/DotAnalyst/releases/latest"
SETUP = "DotAnalyst-Setup.exe"
VERSION = Path(__file__).parent.parent / "VERSION"  # written by packaging\build.ps1 into the bundle


def installed_version() -> str | None:
    """The version of the installed program; None when run from the repo, which never updates itself."""
    return VERSION.read_text().strip() if getattr(sys, "frozen", False) and VERSION.is_file() else None


def parse(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in tag.removeprefix("v").split("."))


def download(client: httpx.Client, current: str, folder: Path) -> Path | None:
    """The newest release's setup when it is newer than `current`, checked against its .sha256; else None."""
    release = client.get(RELEASES, timeout=10).raise_for_status().json()
    if parse(release["tag_name"]) <= parse(current):
        return None
    urls = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
    expected = client.get(urls[f"{SETUP}.sha256"], follow_redirects=True, timeout=30).raise_for_status().text.split()[0]
    setup = client.get(urls[SETUP], follow_redirects=True, timeout=600).raise_for_status().content
    if hashlib.sha256(setup).hexdigest() != expected.lower():  # a cut-off download must not be run
        raise ValueError(f"{SETUP} of {release['tag_name']} does not match its checksum")
    folder.mkdir(exist_ok=True)
    path = folder / SETUP
    path.write_bytes(setup)
    return path


def install(setup: Path, tray: bool = False) -> None:
    """Run the setup on its own, so it outlives this process; it closes a DotAnalyst still running. /TRAY: the app
    was in the tray, so the setup starts it there again afterwards."""
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", *(["/TRAY"] if tray else [])], creationflags=flags)
