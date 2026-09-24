# Dannify release build: frontend -> PyInstaller bundle -> Inno installer.
#
#   pwsh packaging\build.ps1              # full build
#   pwsh packaging\build.ps1 -SkipTests   # skip the frontend test run
#
# Output:
#   Backend\dist\Dannify\            the app folder (what the installer ships)
#   packaging\out\Dannify-Setup-<version>.exe

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root 'frontend'
$backend = Join-Path $root 'Backend'

# One source of truth for the version: the package itself.
$version = (Select-String -Path (Join-Path $backend 'dannify\__init__.py') `
    -Pattern "__version__\s*=\s*'([^']+)'").Matches[0].Groups[1].Value
if (-not $version) { throw 'could not read the version from dannify/__init__.py' }

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Size($path) {
    if (-not (Test-Path $path)) { return 'n/a' }
    $bytes = (Get-ChildItem $path -Recurse -File | Measure-Object Length -Sum).Sum
    '{0:N1} MB' -f ($bytes / 1MB)
}

Step 'Frontend'
Push-Location $frontend
try {
    if (-not $SkipTests) { & npx vitest run }
    & npx vite build
} finally { Pop-Location }

Step 'PyInstaller'
# The exe's version resource is what Properties and Task Manager show. Written
# from the package version rather than kept by hand, because by hand it drifted:
# a 3.12 build was still telling anyone who looked that it was 3.5.
$vparts = ($version -split '[^0-9]+' | Where-Object { $_ }) + @('0', '0', '0', '0')
$vtuple = ($vparts[0..3] -join ', ')
$vinfo = Join-Path $backend 'version_info.txt'
(Get-Content $vinfo -Raw) `
    -replace 'filevers=\([\d, ]+\)', "filevers=($vtuple)" `
    -replace 'prodvers=\([\d, ]+\)', "prodvers=($vtuple)" `
    -replace "StringStruct\('FileVersion', '[^']*'\)", "StringStruct('FileVersion', '$version')" `
    -replace "StringStruct\('ProductVersion', '[^']*'\)", "StringStruct('ProductVersion', '$version')" |
    Set-Content $vinfo -NoNewline

# Same for the installer, for the same reason.
$iss = Join-Path $PSScriptRoot 'dannify.iss'
(Get-Content $iss -Raw) `
    -replace '#define MyAppVersion "[^"]*"', "#define MyAppVersion `"$version`"" |
    Set-Content $iss -NoNewline
Write-Host "  stamped $version into the exe resource and the installer"

Push-Location $backend
try {
    # A stale build/ cache silently keeps removed data files (ffprobe!) around.
    foreach ($dir in 'build', 'dist') {
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    }
    & .\venv\Scripts\python.exe -m PyInstaller --noconfirm --log-level WARN dannify.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
} finally { Pop-Location }

# Packaging metadata names every third-party library and its exact version,
# which is the first thing anyone opening the folder would read. Nothing here
# needs it at runtime: the one library that asks for its own version catches
# the lookup failing. Dropped after the build rather than excluded in the
# spec, because PyInstaller's own hooks put it back.
$runtime = Join-Path $backend 'dist\Dannify\runtime'
if (Test-Path $runtime) {
    Get-ChildItem $runtime -Directory |
        Where-Object { $_.Name -like "*.dist-info" -or $_.Name -like "*.egg-info" } |
        ForEach-Object {
            Write-Host ("  pruned " + $_.Name)
            Remove-Item -Recurse -Force $_.FullName
        }

    # Translated message catalogues for a library we only ever call in English:
    # nothing passes a language, so every one of these but en is 16 folders of
    # nothing, sitting in the install folder under a library's name.
    $locales = Join-Path $runtime 'ytmusicapi\locales'
    if (Test-Path $locales) {
        Get-ChildItem $locales -Directory |
            Where-Object { $_.Name -ne 'en' } |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
        Get-ChildItem $locales -File | Remove-Item -Force
        Write-Host ("  pruned unused locales, kept en")
    }
}
Write-Host ("App folder: " + (Size (Join-Path $backend 'dist\Dannify')))

Step 'Update assets'
# A manifest and a per-file archive, so an update can fetch only what moved
# instead of the whole installer. See Backend/dannify/delta.py.
& (Join-Path $backend 'venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'make_update_assets.py') `
    (Join-Path $backend 'dist\Dannify') $version (Join-Path $PSScriptRoot 'out')
if ($LASTEXITCODE -ne 0) { throw "update assets failed ($LASTEXITCODE)" }

if ($SkipInstaller) { return }

Step 'Installer'
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Warning 'Inno Setup 6 not found: skipping the installer.'
    Write-Warning 'Install it from https://jrsoftware.org/isdl.php and re-run.'
    return
}

Push-Location $PSScriptRoot
try {
    & $iscc 'dannify.iss'
    if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
} finally { Pop-Location }

$setup = Get-ChildItem (Join-Path $PSScriptRoot 'out\Dannify-Setup-*.exe') |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($setup) {
    Write-Host ("Installer: {0} ({1:N1} MB)" -f $setup.Name, ($setup.Length / 1MB)) -ForegroundColor Green
}
