# PyInstaller: build with packaging\build.ps1, or after the parser and the site are built:
#   uv run pyinstaller packaging\dotanalyst.spec --noconfirm
# Output: dist\DotAnalyst\DotAnalyst.exe. The bundle keeps the repo layout (frontend\dist, build\parser) next to the
# dotanalyst package, so the paths api.py and parser.py take from __file__ hold in the exe as well.
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = SPECPATH + "\\.."
# build.ps1 writes build\VERSION; an exe built without it never looks for updates (dotanalyst/update.py)
VERSION = [(ROOT + "\\build\\VERSION", ".")] if os.path.exists(ROOT + "\\build\\VERSION") else []

a = Analysis(
    [ROOT + "\\dotanalyst\\app.py"],
    pathex=[ROOT],
    datas=[(ROOT + "\\frontend\\dist", "frontend\\dist"), (ROOT + "\\build\\parser", "build\\parser")] + VERSION,
    hiddenimports=collect_submodules("uvicorn"),  # uvicorn picks its loop and protocol modules by name
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DotAnalyst", console=False,
          icon=ROOT + "\\packaging\\dotanalyst.ico")  # also the window's: pywebview takes it from the exe
coll = COLLECT(exe, a.binaries, a.datas, name="DotAnalyst")
