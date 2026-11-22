# Builds the installer build\installer\DotAnalyst-Setup.exe: the parser, the site, the exe, then the setup.
# Needs uv, Node.js, git and Inno Setup 6 (winget install JRSoftware.InnoSetup). Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Version 0.1.0
param([string]$Version = "0.0.0")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
Set-Location $root

powershell -ExecutionPolicy Bypass -File packaging\build_parser.ps1
if ($LASTEXITCODE) { throw "parser build failed" }

Push-Location frontend
npm.cmd ci
if ($LASTEXITCODE) { throw "npm ci failed" }
npm.cmd run build
if ($LASTEXITCODE) { throw "site build failed" }
Pop-Location

uv run pyinstaller packaging\dotanalyst.spec --noconfirm --distpath build\dist --workpath build\pyinstaller
if ($LASTEXITCODE) { throw "pyinstaller failed" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found: winget install JRSoftware.InnoSetup" }
& $iscc /Q "/DAppVersion=$Version" packaging\dotanalyst.iss
if ($LASTEXITCODE) { throw "installer build failed" }
Get-Item build\installer\DotAnalyst-Setup.exe
