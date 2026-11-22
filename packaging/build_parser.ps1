# Builds OpenDota's replay parser (github.com/odota/parser) into build\parser: parser.jar, the trimmed Java runtime
# it needs (runtime\), and COMMIT, the parser commit it was built from. JDK 21 and Maven are downloaded once into
# build\tools, so nothing gets installed. Run from anywhere: powershell -File packaging\build_parser.ps1
param([string]$Commit = "master")
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is many times slower with its progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$build = Join-Path (Split-Path $PSScriptRoot) "build"
$tools = Join-Path $build "tools"
New-Item -ItemType Directory -Force $tools | Out-Null

function Get-Checked($url, $file, $algorithm, $expected) {
    Invoke-WebRequest $url -OutFile $file -UseBasicParsing
    $actual = (Get-FileHash $file -Algorithm $algorithm).Hash
    if ($actual -ne $expected.Trim()) { Remove-Item $file; throw "checksum mismatch for $url" }
}

$jdk = Join-Path $tools "jdk"
if (-not (Test-Path "$jdk\bin\jlink.exe")) {
    $asset = (Invoke-RestMethod "https://api.adoptium.net/v3/assets/latest/21/hotspot?os=windows&architecture=x64&image_type=jdk&vendor=eclipse")[0]
    Get-Checked $asset.binary.package.link "$tools\jdk.zip" SHA256 $asset.binary.package.checksum
    Expand-Archive "$tools\jdk.zip" "$tools\jdk-unpacked" -Force
    Move-Item (Get-ChildItem "$tools\jdk-unpacked" -Directory)[0].FullName $jdk
    Remove-Item "$tools\jdk.zip", "$tools\jdk-unpacked" -Recurse
}
$maven = Join-Path $tools "maven"
if (-not (Test-Path "$maven\bin\mvn.cmd")) {
    $url = "https://archive.apache.org/dist/maven/maven-3/3.9.12/binaries/apache-maven-3.9.12-bin.zip"
    Get-Checked $url "$tools\maven.zip" SHA512 ((Invoke-WebRequest "$url.sha512" -UseBasicParsing).Content -split '\s')[0]
    Expand-Archive "$tools\maven.zip" $tools -Force
    Move-Item "$tools\apache-maven-3.9.12" $maven
    Remove-Item "$tools\maven.zip"
}
$env:JAVA_HOME = $jdk

$src = Join-Path $build "parser-src"
if (Test-Path $src) { Remove-Item $src -Recurse -Force }
git clone --quiet https://github.com/odota/parser.git $src
if ($LASTEXITCODE) { throw "git clone failed" }
git -C $src checkout --quiet $Commit
if ($LASTEXITCODE) { throw "no parser commit $Commit" }

# The parser listens on every network interface and fetches any URL it is sent: keep it to this computer.
# Docker did that with its port mapping (127.0.0.1:5600:5600); run without Docker, the code has to.
$main = Join-Path $src "src\main\java\opendota\Main.java"
$code = [IO.File]::ReadAllText($main)
$listen = 'new InetSocketAddress(Integer.valueOf("5600"))'
if (-not $code.Contains($listen)) { throw "Main.java no longer has $listen; update the localhost patch in $PSCommandPath" }
[IO.File]::WriteAllText($main, $code.Replace($listen, 'new InetSocketAddress(java.net.InetAddress.getLoopbackAddress(), 5600)'))

& "$maven\bin\mvn.cmd" -q -f "$src\pom.xml" clean package
if ($LASTEXITCODE) { throw "maven build failed" }
$jar = Join-Path $src "target\stats-0.1.0.jar"

$out = Join-Path $build "parser"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory $out | Out-Null
# the jar carries clarity's module-info.class, which makes jdeps take it for a module: look at a copy without it
$plain = Join-Path $src "target\plain.jar"
Copy-Item $jar $plain
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::Open($plain, "Update")
@($zip.Entries | Where-Object { $_.FullName -match '(^|/)module-info\.class$' }) | ForEach-Object { $_.Delete() }
$zip.Dispose()
$modules = & "$jdk\bin\jdeps.exe" --print-module-deps --ignore-missing-deps --multi-release 21 $plain
if ($LASTEXITCODE) { throw "jdeps failed" }
& "$jdk\bin\jlink.exe" --add-modules $modules --strip-debug --no-man-pages --no-header-files --compress zip-6 --output "$out\runtime"
if ($LASTEXITCODE) { throw "jlink failed" }
Copy-Item $jar "$out\parser.jar"
git -C $src rev-parse HEAD | Set-Content "$out\COMMIT" -Encoding ascii
Write-Host "parser $(Get-Content "$out\COMMIT") built into $out (Java modules: $modules)"
