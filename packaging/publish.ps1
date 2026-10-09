# Publish a release on Dannify's repository, beside every release before it.
# Installed copies update from its latest release.
#
#   pwsh packaging\publish.ps1 -Notes "what changed"
#   pwsh packaging\publish.ps1 -Notes (Get-Content notes.md -Raw)
#
# One release carries every platform: the Windows setup and package built
# here by build.ps1, and the Linux .deb and macOS apps the release workflow
# builds on GitHub's machines when the tag is pushed. Those come down
# unsigned: they are signed here, with the offline release key that never
# goes near GitHub, and every file is checked against the key installed
# copies trust before anything is uploaded.
#
# Up to 4.6.1, builds went to a separate repository, dannify-releases, that
# carried the current build and nothing else, while the source was private.
# The source is public now; 4.6.2 was the last build put there as well, so
# that every copy installed from it could find its way here.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Notes,
    # The tag is pushed with the merge, before this runs.
    [string]$Repo = 'DANIELMWENDWA9451/Dannify',
    # The platforms this release must carry. Leaving one out is a decision,
    # never something that happens because its build failed.
    [string[]]$Platforms = @('windows', 'linux', 'macos'),
    # How long to wait for the release workflow to finish building.
    [int]$WaitMinutes = 90
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $PSScriptRoot 'out'
$python = Join-Path $root 'Backend\venv\Scripts\python.exe'
$releaseKey = Join-Path $PSScriptRoot 'release_key.py'
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
if (-not (Test-Path $gh)) { $gh = 'gh' }

$version = (Select-String -Path (Join-Path $root 'Backend\dannify\__init__.py') `
    -Pattern "__version__\s*=\s*'([^']+)'").Matches[0].Groups[1].Value
if (-not $version) { throw 'could not read the version' }
$tag = "v$version"

$files = @()
if ($Platforms -contains 'windows') {
    # The installer (new installs, and Dannify 3.x moving to 4.0) and the
    # package installed copies update from. Deliberately not manifest-* or
    # files-*: 3.x would try to patch its old layout with those.
    $files += @(
        (Join-Path $out "Dannify-Setup-$version.exe"),
        (Join-Path $out "Dannify-Setup-$version.exe.sig"),
        (Join-Path $out "package-$version.json"),
        (Join-Path $out "package-$version.json.sig"),
        (Join-Path $out "package-$version.zip")
    )
    foreach ($f in $files) { if (-not (Test-Path $f)) { throw "missing $f (run build.ps1)" } }
}

# --- Linux and macOS: built by the release workflow for this tag -----------
$wanted = @()
if ($Platforms -contains 'linux') { $wanted += "linux-dannify_${version}_amd64.deb" }
if ($Platforms -contains 'macos') {
    foreach ($arch in 'arm64', 'x64') {
        $wanted += "macos-Dannify-$version-$arch.zip", "macos-Dannify-$version-$arch.dmg"
    }
}
if ($wanted) {
    $sha = (& git -c safe.directory=* -C $root rev-list -n 1 $tag).Trim()
    if (-not $sha) { throw "no tag $tag here; push it first" }
    Write-Host "Waiting for the release workflow on $tag ($($sha.Substring(0, 9)))" -ForegroundColor Cyan
    $deadline = (Get-Date).AddMinutes($WaitMinutes)
    $run = $null
    while (-not $run) {
        $runs = & $gh run list --repo $Repo --workflow release.yml --limit 30 --json databaseId,headSha,status,conclusion,event | ConvertFrom-Json
        $run = $runs | Where-Object { $_.headSha -eq $sha -and $_.event -in @('push', 'workflow_dispatch') } | Select-Object -First 1
        if ($run -and $run.status -ne 'completed') {
            if ((Get-Date) -gt $deadline) { throw 'the release workflow did not finish in time' }
            & $gh run watch $run.databaseId --repo $Repo --exit-status --interval 30 | Out-Null
            $run = $null
            continue
        }
        if (-not $run) {
            if ((Get-Date) -gt $deadline) { throw "no release workflow run for $tag" }
            Start-Sleep -Seconds 20
        }
    }
    if ($run.conclusion -ne 'success') { throw "the release workflow for $tag ended: $($run.conclusion)" }

    $ci = Join-Path $out "ci-$version"
    if (Test-Path $ci) { Remove-Item $ci -Recurse -Force }
    & $gh run download $run.databaseId --repo $Repo --dir $ci
    if ($LASTEXITCODE -ne 0) { throw 'could not download the workflow builds' }
    foreach ($name in $wanted) {
        $found = Get-ChildItem -Path $ci -Recurse -File -Filter $name | Select-Object -First 1
        if (-not $found) { throw "the workflow did not build $name" }
        $dest = Join-Path $out $name
        Copy-Item $found.FullName $dest -Force
        $files += $dest
    }

    # Signed here, with the offline key. release_key.py refuses to sign with
    # any key but the one installed copies trust.
    Write-Host 'Signing the Linux and macOS builds' -ForegroundColor Cyan
    $toSign = $wanted | ForEach-Object { Join-Path $out $_ }
    & $python $releaseKey sign-release @toSign
    if ($LASTEXITCODE -ne 0) { throw 'signing the platform builds failed' }
    $files += $toSign | ForEach-Object { "$_.sig" }
}

# --- Every file checked against the key the app carries --------------------
# Every installed copy from 4.7.0 on refuses an update that does not verify,
# so a release that would be refused everywhere is never put up at all.
$signed = $files | Where-Object { $_ -notlike '*.sig' -and $_ -notlike '*package-*.zip' }
& $python $releaseKey verify-release @signed
if ($LASTEXITCODE -ne 0) { throw 'a release file does not verify against PUBLIC_KEY in updates.py' }

Write-Host "Publishing $tag on $Repo with $($files.Count) files" -ForegroundColor Cyan
& $gh release create $tag --repo $Repo --verify-tag --latest --title "Dannify $version" --notes $Notes @files
if ($LASTEXITCODE -ne 0) { throw "gh release create failed ($LASTEXITCODE)" }

Write-Host "Done. $tag is the latest release on $Repo." -ForegroundColor Green
