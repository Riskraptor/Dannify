# Publish a release on Dannify's repository, beside every release before it.
# Installed copies update from its latest release.
#
#   pwsh packaging/publish.ps1 -Notes "what changed"
#   pwsh packaging/publish.ps1 -Notes (Get-Content notes.md -Raw)
#
# Runs wherever PowerShell does: releases are cut from Linux now.
#
# One release carries every platform: the Windows setup and package, the
# Linux .deb, the macOS apps and the Android APKs, all built by the release
# workflow on GitHub's machines when the tag is pushed. They come down
# unsigned: they are signed here, with the offline release key that never
# goes near GitHub, and every file is checked against the key installed
# copies trust before anything is uploaded. The APKs are signed first with
# the Android app's own key, which stays here too (see android/README.md).
#
# The Android signing needs the Android SDK's build-tools (apksigner, which
# runs on Java: JAVA_HOME), and the app's key: DANNIFY_APK_KEYSTORE names it
# (default ~/.dannify/dannify.keystore), and its password is in
# DANNIFY_APK_KEYSTORE_PASSWORD or in a file beside it, <keystore>.password.
#
# -WindowsFrom local takes the Windows files from packaging\out instead, as
# build.ps1 leaves them on a Windows desk, already signed.
#
# Up to 4.6.1, builds went to a separate repository, dannify-releases, that
# carried the current build and nothing else, while the source was private.
# The source is public now; 4.6.2 was the last build put there as well, so
# that every copy installed from it could find its way here.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Notes,
    # The tag is pushed with the merge, before this runs.
    [string]$Repo = 'Riskraptor/Dannify',
    # The platforms this release must carry. Leaving one out is a decision,
    # never something that happens because its build failed.
    [ValidateSet('windows', 'linux', 'macos', 'android')][string[]]$Platforms = @('windows', 'linux', 'macos', 'android'),
    # Where the Windows files come from: the release workflow, or a build.ps1
    # run on this machine.
    [ValidateSet('ci', 'local')][string]$WindowsFrom = 'ci',
    # How long to wait for the release workflow to finish building.
    [int]$WaitMinutes = 90,
    # Download, sign and check everything, then stop: nothing is published.
    [switch]$DryRun,
    # With -DryRun: take the builds from this workflow run rather than the
    # tag's own, to try the whole thing out on a branch.
    [Alias('FromRun')][string]$Run = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $PSScriptRoot 'out'
# Where the workflow's builds are put and signed. A dry run keeps to a folder
# of its own: on a branch it carries the version of a release already made,
# and must not write over that release's files.
$work = if ($DryRun) { Join-Path $out 'dry-run' } else { $out }
New-Item -ItemType Directory -Force $work | Out-Null
# The Python the signing runs on: the one named, or this checkout's own
# environment. Its place for this system only (Scripts on Windows, bin
# everywhere else): a checkout that has moved between the two can hold both.
$python = $env:DANNIFY_PYTHON
$own = Join-Path $root $(if ($env:OS -eq 'Windows_NT') { 'Backend/venv/Scripts/python.exe' } else { 'Backend/venv/bin/python' })
if (-not $python -and (Test-Path $own)) { $python = $own }
if (-not $python) { throw 'no Python to sign with: make Backend/venv (see the README) or set DANNIFY_PYTHON' }
$releaseKey = Join-Path $PSScriptRoot 'release_key.py'
# What release_key.py calls a signature file (signing.SIGNATURE_SUFFIX).
$sig = '.dsig'
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
if (-not (Test-Path $gh)) { $gh = 'gh' }

$version = (Select-String -Path (Join-Path $root 'Backend/dannify/__init__.py') `
    -Pattern "__version__\s*=\s*'([^']+)'").Matches[0].Groups[1].Value
if (-not $version) { throw 'could not read the version' }
$tag = "v$version"

# No point waiting on a build for a key that is not there.
& $python $releaseKey public | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'no release signing key (see packaging/release_key.py)' }

# The installer (new installs, and Dannify 3.x moving to 4.0) and the package
# installed copies update from. Deliberately not manifest-* or files-*: 3.x
# would try to patch its old layout with those.
$windows = @("Dannify-Setup-$version.exe", "package-$version.json", "package-$version.zip")
$files = @()
$wanted = @()
if ($Platforms -contains 'windows') {
    if ($WindowsFrom -eq 'local') {
        $files += @(
            (Join-Path $out "Dannify-Setup-$version.exe"),
            (Join-Path $out "Dannify-Setup-$version.exe$sig"),
            (Join-Path $out "package-$version.json"),
            (Join-Path $out "package-$version.json$sig"),
            (Join-Path $out "package-$version.zip")
        )
        foreach ($f in $files) { if (-not (Test-Path $f)) { throw "missing $f (run build.ps1)" } }
    } else {
        $wanted += $windows
    }
}

# --- Built by the release workflow for this tag -----------------------------
if ($Platforms -contains 'linux') { $wanted += "linux-dannify_${version}_amd64.deb" }
if ($Platforms -contains 'macos') {
    foreach ($arch in 'arm64', 'x64') {
        $wanted += "macos-Dannify-$version-$arch.zip", "macos-Dannify-$version-$arch.dmg"
    }
}
$apks = @()
if ($Platforms -contains 'android') {
    $apks = @('arm64', 'x86_64') | ForEach-Object { "android-Dannify-$version-$_.apk" }
    $wanted += $apks
}

# Everything the Android signing needs is checked before any waiting.
if ($apks) {
    $sdk = @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, (Join-Path $HOME 'Android/sdk')) |
        Where-Object { $_ -and (Test-Path (Join-Path $_ 'build-tools')) } | Select-Object -First 1
    if (-not $sdk) { throw "no Android SDK build-tools for apksigner (set ANDROID_HOME)" }
    $apksigner = Get-ChildItem (Join-Path $sdk 'build-tools') -Directory |
        Sort-Object { [version](($_.Name -replace '-.*$', '') + '.0' * (3 - ($_.Name -replace '-.*$', '').Split('.').Count)) } -Descending |
        ForEach-Object { Join-Path $_.FullName $(if ($env:OS -eq 'Windows_NT') { 'apksigner.bat' } else { 'apksigner' }) } |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $apksigner) { throw "no apksigner in $sdk/build-tools" }
    $keystore = if ($env:DANNIFY_APK_KEYSTORE) { $env:DANNIFY_APK_KEYSTORE } else { Join-Path $HOME '.dannify/dannify.keystore' }
    if (-not (Test-Path $keystore)) { throw "no Android signing key at $keystore (DANNIFY_APK_KEYSTORE)" }
    # The password is handed over by name, never on a command line.
    $keyPass = if ($env:DANNIFY_APK_KEYSTORE_PASSWORD) { 'env:DANNIFY_APK_KEYSTORE_PASSWORD' } else { "file:$keystore.password" }
    if (-not $env:DANNIFY_APK_KEYSTORE_PASSWORD -and -not (Test-Path "$keystore.password")) {
        throw "no password for $keystore (DANNIFY_APK_KEYSTORE_PASSWORD, or $keystore.password)"
    }
    # The certificate every Dannify APK has ever been signed with. Android
    # installs an update only over an app signed with the same key: an APK
    # signed with any other could never update a single phone.
    $certificate = (Get-Content (Join-Path $PSScriptRoot 'android/certificate.sha256') -Raw).Trim().ToLower()
}
if ($Run -and -not $DryRun) { throw '-Run is for -DryRun only: a release carries the builds of its own tag' }
if ($wanted) {
    $requestedRun = $Run
    $workflowRun = $null
    if ($requestedRun) {
        $workflowRun = & $gh run view $requestedRun --repo $Repo --json databaseId,status,conclusion | ConvertFrom-Json
        if (-not $workflowRun -or $workflowRun.status -ne 'completed') { throw "workflow run $requestedRun has not finished" }
    } else {
        $sha = (& git -c safe.directory=* -C $root rev-list -n 1 $tag).Trim()
        if (-not $sha) { throw "no tag $tag here; push it first" }
        Write-Host "Waiting for the release workflow on $tag ($($sha.Substring(0, 9)))" -ForegroundColor Cyan
        $deadline = (Get-Date).AddMinutes($WaitMinutes)
    }
    while (-not $workflowRun) {
        $runs = & $gh run list --repo $Repo --workflow release.yml --limit 30 --json databaseId,headSha,status,conclusion,event | ConvertFrom-Json
        $workflowRun = $runs | Where-Object { $_.headSha -eq $sha -and $_.event -in @('push', 'workflow_dispatch') } | Select-Object -First 1
        if ($workflowRun -and $workflowRun.status -ne 'completed') {
            if ((Get-Date) -gt $deadline) { throw 'the release workflow did not finish in time' }
            & $gh run watch $workflowRun.databaseId --repo $Repo --exit-status --interval 30 | Out-Null
            $workflowRun = $null
            continue
        }
        if (-not $workflowRun) {
            if ((Get-Date) -gt $deadline) { throw "no release workflow run for $tag" }
            Start-Sleep -Seconds 20
        }
    }
    if ($workflowRun.conclusion -ne 'success') { throw "the release workflow for $tag ended: $($workflowRun.conclusion)" }

    $ci = Join-Path $work "ci-$version"
    if (Test-Path $ci) { Remove-Item $ci -Recurse -Force }
    # Only what this release carries: the run also keeps screenshots and
    # parts of its own, and every megabyte comes down this machine's line.
    $names = $wanted | ForEach-Object { '--name', $_ }
    & $gh run download $workflowRun.databaseId --repo $Repo --dir $ci @names
    if ($LASTEXITCODE -ne 0) { throw 'could not download the workflow builds' }
    foreach ($name in $wanted) {
        $found = Get-ChildItem -Path $ci -Recurse -File -Filter $name | Select-Object -First 1
        if (-not $found) { throw "the workflow did not build $name" }
        $dest = Join-Path $work $name
        Copy-Item $found.FullName $dest -Force
        $files += $dest
    }

    # The APKs first get the Android app's own signature, which the release
    # signature below then covers with the rest of the file.
    foreach ($name in $apks) {
        $apk = Join-Path $work $name
        Write-Host "Signing $name for Android" -ForegroundColor Cyan
        & $apksigner sign --ks $keystore --ks-pass $keyPass --ks-key-alias dannify --v4-signing-enabled false $apk
        if ($LASTEXITCODE -ne 0) { throw "signing $name for Android failed" }
        $printed = & $apksigner verify --print-certs $apk
        if ($LASTEXITCODE -ne 0) { throw "$name does not verify as an APK" }
        $found = $printed | Select-String 'certificate SHA-256 digest: ([0-9a-f]{64})' | Select-Object -First 1
        $digest = if ($found) { $found.Matches[0].Groups[1].Value } else { '' }
        if ($digest -ne $certificate) { throw "$name is signed with another key ($digest), not the app's ($certificate)" }
    }

    # Signed here, with the offline key. release_key.py refuses to sign with
    # any key but the one installed copies trust. The package archive has no
    # signature of its own: the signed list names the hash of every file in it.
    Write-Host 'Signing the builds' -ForegroundColor Cyan
    $toSign = $wanted | Where-Object { $_ -notlike 'package-*.zip' } | ForEach-Object { Join-Path $work $_ }
    & $python $releaseKey sign-release @toSign
    if ($LASTEXITCODE -ne 0) { throw 'signing the platform builds failed' }
    $files += $toSign | ForEach-Object { "$_$sig" }
}

# --- Every file checked against the key the app carries --------------------
# Every installed copy from 4.7.0 on refuses an update that does not verify,
# so a release that would be refused everywhere is never put up at all.
$signed = $files | Where-Object { $_ -notlike "*$sig" -and $_ -notlike '*package-*.zip' }
& $python $releaseKey verify-release @signed
if ($LASTEXITCODE -ne 0) { throw 'a release file does not verify against PUBLIC_KEY in updates.py' }

# --- The release, described by itself -------------------------------------
# What installed copies read first (updates._from_description). GitHub's API
# answers 60 times an hour per address, shared by everyone behind one router
# (often a whole mobile network), and up to 4.14.1 a copy that was refused
# said "Could not check for updates" until the hour turned. This file is
# fetched like any download, from /releases/latest/download/, with no such
# limit. Its every file is still checked against its signature before use.
$described = Join-Path $work 'latest.json'
$assets = @($files | ForEach-Object {
    $leaf = Split-Path $_ -Leaf
    [ordered]@{
        name                 = $leaf
        size                 = (Get-Item $_).Length
        browser_download_url = "https://github.com/$Repo/releases/download/$tag/$leaf"
    }
})
[ordered]@{
    tag_name     = $tag
    name         = "Dannify $version"
    body         = $Notes
    html_url     = "https://github.com/$Repo/releases/tag/$tag"
    published_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    assets       = $assets
} | ConvertTo-Json -Depth 5 | Set-Content -Path $described -Encoding utf8NoBOM
$files += $described

if ($DryRun) {
    Write-Host "Dry run: $($files.Count) files signed and checked, nothing published." -ForegroundColor Green
    $files | ForEach-Object { '  ' + (Split-Path $_ -Leaf) }
    return
}

Write-Host "Publishing $tag on $Repo with $($files.Count) files" -ForegroundColor Cyan
& $gh release create $tag --repo $Repo --verify-tag --latest --title "Dannify $version" --notes $Notes @files
if ($LASTEXITCODE -ne 0) { throw "gh release create failed ($LASTEXITCODE)" }

Write-Host "Done. $tag is the latest release on $Repo." -ForegroundColor Green
