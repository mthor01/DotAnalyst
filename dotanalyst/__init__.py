import os
from pathlib import Path


def load_env(path: Path = Path(".env")) -> None:
    """Put the KEY=VALUE lines of .env, when there is one, into the environment; a variable set already wins.

    The commands and the server call it, not the package import, so the tests never pick up the real keys.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        name, value = name.strip().removeprefix("export ").strip(), value.strip()
        if not sep or not name or name.startswith("#"):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(name, value)
