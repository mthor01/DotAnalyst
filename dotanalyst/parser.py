"""The replay parser, started with the server: the bundled one in build/parser (packaging/build_parser.ps1 builds it),
unless a parser answers already, such as one run in Docker."""
import logging
import subprocess
import time
from pathlib import Path

import httpx

from .db import DATA
from .replay import PARSER_URL

PARSER_DIR = Path(__file__).parent.parent / "build" / "parser"
log = logging.getLogger(__name__)


def answers() -> bool:
    try:
        httpx.get(f"{PARSER_URL}healthz", timeout=1)
        return True
    except httpx.HTTPError:
        return False


def start(parser_dir: Path = PARSER_DIR, wait: float = 30) -> subprocess.Popen | None:
    """Start the bundled parser and wait until it answers, so the first replay is not marked tried while it starts.
    None when another parser answers or none is bundled."""
    if answers():
        # shortcut: one left running by a crashed app is used and never stopped, use a job object if that piles up
        return None
    java = parser_dir / "runtime" / "bin" / "java.exe"
    if not java.is_file():
        log.warning("no parser in %s and none answers at %s: replays are not parsed", parser_dir, PARSER_URL)
        return None
    DATA.mkdir(exist_ok=True)
    with open(DATA / "parser.log", "ab") as out:  # the child keeps its own handle
        process = subprocess.Popen(
            # the flags of the parser's Docker image, without its memory share: on a desktop Java's default is kinder
            [java, "-XX:-UseCompressedClassPointers", "-XX:+ExitOnOutOfMemoryError", "-jar", parser_dir / "parser.jar", "5600"],
            stdout=out, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    deadline = time.monotonic() + wait
    while process.poll() is None and time.monotonic() < deadline and not answers():
        time.sleep(0.2)
    return process


def stop(process: subprocess.Popen | None) -> None:
    if process is not None:
        process.terminate()
        process.wait(10)
