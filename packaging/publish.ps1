# Publish a release: on the public repository (where installed copies update
# from), leaving only that one there, and on the private one, beside every
# release before it.
#
#   pwsh packaging\publish.ps1 -Notes "what changed"
#   pwsh packaging\publish.ps1 -Notes (Get-Content notes.md -Raw)
#
# The private repository keeps every tag, so any version can be rebuilt. The
# public one carries the current build and nothing else: that is the whole
# point of it being separate.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Notes,
    [string]$Repo = 'DANIELMWENDWA9451/dannify-releases',
    # Where the source is. Its tag is pushed with the merge, before this runs.
    [string]$PrivateRepo = 'DANIELMWENDWA9451/Dannify',
    [switch]$KeepOld
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $PSScriptRoot 'out'

$version = (Select-String -Path (Join-Path $root 'Backend\dannify\__init__.py') `
    -Pattern "__version__\s*=\s*'([^']+)'").Matches[0].Groups[1].Value
if (-not $version) { throw 'could not read the version' }

$tag = "v$version"
# The installer (new installs, and Dannify 3.x moving to 4.0) and the package
# installed copies update from. Deliberately not manifest-*/files-*: 3.x
# would try to patch its old layout with those, instead of taking the
# installer that moves it to the new one.
$files = @(
    (Join-Path $out "Dannify-Setup-$version.exe"),
    (Join-Path $out "package-$version.json"),
    (Join-Path $out "package-$version.zip")
)
foreach ($f in $files) { if (-not (Test-Path $f)) { throw "missing $f" } }

Write-Host "Publishing $tag" -ForegroundColor Cyan
& gh release create $tag --repo $Repo --title "Dannify $version" --notes $Notes @files
if ($LASTEXITCODE -ne 0) { throw "gh release create failed ($LASTEXITCODE)" }

# The same release on the private repository, kept with every earlier one,
# so its Releases page shows what was shipped. It stopped at 3.2.0 for a
# whole series of releases when only the public one was published.
if ($PrivateRepo) {
    Write-Host "Publishing $tag on $PrivateRepo" -ForegroundColor Cyan
    & gh release create $tag --repo $PrivateRepo --verify-tag --latest --title "Dannify $version" --notes $Notes @files
    if ($LASTEXITCODE -ne 0) { throw "gh release create on $PrivateRepo failed ($LASTEXITCODE)" }
}

if ($KeepOld) { return }

Write-Host 'Removing older releases' -ForegroundColor Cyan
$old = & gh release list --repo $Repo --limit 100 --json tagName --jq '.[].tagName' |
    Where-Object { $_ -and $_ -ne $tag }
foreach ($t in $old) {
    & gh release delete $t --repo $Repo --cleanup-tag --yes
    Write-Host "  removed $t"
}

Write-Host "Done. Only $tag is on the releases page now." -ForegroundColor Green
