# PyInstaller: build with packaging\build.ps1, or after the parser and the site are built:
#   uv run pyinstaller packaging\dotanalyst.spec --noconfirm
# Output: dist\DotAnalyst\DotAnalyst.exe. The bundle keeps the repo layout (frontend\dist, build\parser) next to the
# dotanalyst package, so the paths api.py and parser.py take from __file__ hold in the exe as well.
from PyInstaller.utils.hooks import collect_submodules

ROOT = SPECPATH + "\\.."

a = Analysis(
    [ROOT + "\\dotanalyst\\app.py"],
    pathex=[ROOT],
    datas=[(ROOT + "\\frontend\\dist", "frontend\\dist"), (ROOT + "\\build\\parser", "build\\parser")],
    hiddenimports=collect_submodules("uvicorn"),  # uvicorn picks its loop and protocol modules by name
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DotAnalyst", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="DotAnalyst")
