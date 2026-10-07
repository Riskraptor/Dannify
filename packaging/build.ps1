# Dannify release build: frontend -> PyInstaller bundle -> installer.
#
#   pwsh packaging\build.ps1              # full build
#   pwsh packaging\build.ps1 -SkipTests   # skip the test runs
#
# Output:
#   Backend\dist\Dannify\                    the app folder (installed as <root>\app)
#   packaging\out\Dannify-Setup-<v>.exe      the installer: our own, see installer\
#   packaging\out\package-<v>.json/.zip      what installed copies update from
#   packaging\out\*.sig                      release signatures (release_key.py)

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root 'frontend'
$backend = Join-Path $root 'Backend'
$installer = Join-Path $root 'installer'
$out = Join-Path $PSScriptRoot 'out'
$python = Join-Path $backend 'venv\Scripts\python.exe'

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

$dotnet = (Get-Command dotnet -ErrorAction SilentlyContinue).Source
if (-not $dotnet) { $dotnet = Join-Path $env:ProgramFiles 'dotnet\dotnet.exe' }
if (-not (Test-Path $dotnet)) { throw 'the .NET SDK is needed to build the installer (dotnet not found)' }

# Without the release key there is no point building: nothing it makes could
# be installed as an update. Found out now rather than after PyInstaller.
if (-not $SkipInstaller) {
    & $python (Join-Path $PSScriptRoot 'release_key.py') public | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'no release signing key (see packaging\release_key.py)' }
}

if (-not $SkipTests) {
    Step 'Backend tests'
    Push-Location $backend
    try {
        & $python -m pytest -q -p no:cacheprovider
        if ($LASTEXITCODE -ne 0) { throw "backend tests failed ($LASTEXITCODE)" }
    } finally { Pop-Location }
}

Step 'Frontend'
Push-Location $frontend
try {
    if (-not $SkipTests) {
        & npx vitest run
        if ($LASTEXITCODE -ne 0) { throw "frontend tests failed ($LASTEXITCODE)" }
    }
    & npx vite build
    if ($LASTEXITCODE -ne 0) { throw "frontend build failed ($LASTEXITCODE)" }
} finally { Pop-Location }

Step 'Version'
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

# Same for the installer, which is also the launcher and the uninstaller.
$csproj = Join-Path $installer 'Dannify.Setup.csproj'
$numeric = ($vparts[0..2] -join '.')
(Get-Content $csproj -Raw) `
    -replace '<Version>[^<]*</Version>', "<Version>$numeric</Version>" |
    Set-Content $csproj -NoNewline
Write-Host "  stamped $version into the app and the installer"

Step 'PyInstaller'
Push-Location $backend
try {
    # A stale build/ cache silently keeps removed data files (ffprobe!) around.
    foreach ($dir in 'build', 'dist') {
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    }
    & $python -m PyInstaller --noconfirm --log-level WARN dannify.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
} finally { Pop-Location }

$app = Join-Path $backend 'dist\Dannify'
$runtime = Join-Path $app 'runtime'

# Packaging metadata names every third-party library and its exact version,
# which is the first thing anyone opening the folder would read. Nothing here
# needs it at runtime: the one library that asks for its own version catches
# the lookup failing. Dropped after the build rather than excluded in the
# spec, because PyInstaller's own hooks put it back.
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

# Where updates come from and the support link are built into the app (see
# updates.py, support.py): nothing in the install folder can be edited to
# point them elsewhere. packaging\config is read by development runs only.

# Dannify's licence, and the notices the open-source parts inside it ask to
# travel with them, beside the program.
$repoRoot = Split-Path $PSScriptRoot -Parent
foreach ($notice in 'LICENSE', 'THIRD-PARTY-NOTICES.md') {
    Copy-Item (Join-Path $repoRoot $notice) (Join-Path $app $notice) -Force
}

Step 'Installer program'
& $dotnet build $csproj -c Release -nologo -v q
if ($LASTEXITCODE -ne 0) { throw "installer build failed ($LASTEXITCODE)" }
$engine = Join-Path $installer 'bin\Release\DannifySetup.exe'
if (-not (Test-Path $engine)) { throw "installer program missing: $engine" }
# The launcher travels inside the app, so an update can bring a new one.
Copy-Item $engine (Join-Path $runtime 'launcher.exe') -Force
Write-Host ("App folder: " + (Size $app))

Step 'Update package'
New-Item -ItemType Directory -Force $out | Out-Null
& $python (Join-Path $PSScriptRoot 'make_update_assets.py') $app $version $out
if ($LASTEXITCODE -ne 0) { throw "update package failed ($LASTEXITCODE)" }

if ($SkipInstaller) { return }

Step 'Installer'
$setup = Join-Path $out "Dannify-Setup-$version.exe"
& $python (Join-Path $PSScriptRoot 'make_setup.py') $app $version $engine $setup
if ($LASTEXITCODE -ne 0) { throw "installer packing failed ($LASTEXITCODE)" }

# Unpack the whole thing into a scratch folder and hash every file against
# its list, exactly as an install would, before anything gets published.
$check = Join-Path ([IO.Path]::GetTempPath()) ("dannify-build-check-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
$verify = Start-Process -FilePath $setup -ArgumentList @('--verify-payload', '--data', $check) -Wait -PassThru
Remove-Item -Recurse -Force $check -ErrorAction SilentlyContinue
if ($verify.ExitCode -ne 0) { throw "the installer failed its own check ($($verify.ExitCode))" }

# Windows code signing, when a certificate is available. SmartScreen warns
# about any setup that is not signed. The signature goes on the end of the
# file, after the payload; the installer reads past it (see Payload.cs).
#   DANNIFY_SIGN_THUMBPRINT  a code-signing certificate in CurrentUser\My
#   DANNIFY_TIMESTAMP_URL    optional, default http://timestamp.digicert.com
if ($env:DANNIFY_SIGN_THUMBPRINT) {
    Step 'Code signing'
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Thumbprint -eq $env:DANNIFY_SIGN_THUMBPRINT } | Select-Object -First 1
    if (-not $cert) { throw "no code-signing certificate $($env:DANNIFY_SIGN_THUMBPRINT) in CurrentUser\My" }
    $stamp = if ($env:DANNIFY_TIMESTAMP_URL) { $env:DANNIFY_TIMESTAMP_URL } else { 'http://timestamp.digicert.com' }
    $signed = Set-AuthenticodeSignature -FilePath $setup -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $stamp
    if ($signed.Status -ne 'Valid') { throw "code signing failed: $($signed.StatusMessage)" }
    # Signed, it must still unpack and check out exactly as before.
    $check = Join-Path ([IO.Path]::GetTempPath()) ("dannify-build-check-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    $verify = Start-Process -FilePath $setup -ArgumentList @('--verify-payload', '--data', $check) -Wait -PassThru
    Remove-Item -Recurse -Force $check -ErrorAction SilentlyContinue
    if ($verify.ExitCode -ne 0) { throw "the signed installer failed its own check ($($verify.ExitCode))" }
    Write-Host "  signed by $($cert.Subject)"
} else {
    Write-Host "`n  (no DANNIFY_SIGN_THUMBPRINT: the installer is not code-signed; SmartScreen will warn)" -ForegroundColor Yellow
}

# Dannify's own release signatures: what installed copies check every update
# against (see Backend/dannify/signing.py). Last, because they cover the final
# bytes of each file. A release without them would be refused by every copy.
Step 'Release signatures'
$manifestFile = Join-Path $out "package-$version.json"
& $python (Join-Path $PSScriptRoot 'release_key.py') sign package $version $manifestFile
if ($LASTEXITCODE -ne 0) { throw "signing the package list failed ($LASTEXITCODE)" }
& $python (Join-Path $PSScriptRoot 'release_key.py') sign installer $version $setup
if ($LASTEXITCODE -ne 0) { throw "signing the installer failed ($LASTEXITCODE)" }
# Checked against the key the app itself carries, not the one just used:
# a release signed with any other key would install nowhere.
$shipped = (Select-String -Path (Join-Path $backend 'dannify\updates.py') -Pattern "^PUBLIC_KEY = '([0-9a-f]+)'$").Matches[0].Groups[1].Value
if (-not $shipped) { throw 'updates.py carries no PUBLIC_KEY' }
$env:DANNIFY_RELEASE_PUBLIC = $shipped
try {
    & $python (Join-Path $PSScriptRoot 'release_key.py') verify package $version $manifestFile
    if ($LASTEXITCODE -ne 0) { throw 'the package list does not verify against the key in updates.py' }
    & $python (Join-Path $PSScriptRoot 'release_key.py') verify installer $version $setup
    if ($LASTEXITCODE -ne 0) { throw 'the installer does not verify against the key in updates.py' }
} finally { Remove-Item Env:\DANNIFY_RELEASE_PUBLIC -ErrorAction SilentlyContinue }

$file = Get-Item $setup
Write-Host ("Installer: {0} ({1:N1} MB), checked" -f $file.Name, ($file.Length / 1MB)) -ForegroundColor Green
