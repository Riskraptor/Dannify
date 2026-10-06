# Publish a release on Dannify's repository, beside every release before it.
# Installed copies update from its latest release.
#
#   pwsh packaging\publish.ps1 -Notes "what changed"
#   pwsh packaging\publish.ps1 -Notes (Get-Content notes.md -Raw)
#
# Up to 4.6.1, builds went to a separate repository, dannify-releases, that
# carried the current build and nothing else, while the source was private.
# The source is public now; 4.6.2 was the last build put there as well, so
# that every copy installed from it could find its way here.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Notes,
    # The tag is pushed with the merge, before this runs.
    [string]$Repo = 'DANIELMWENDWA9451/Dannify'
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

Write-Host "Publishing $tag on $Repo" -ForegroundColor Cyan
& gh release create $tag --repo $Repo --verify-tag --latest --title "Dannify $version" --notes $Notes @files
if ($LASTEXITCODE -ne 0) { throw "gh release create failed ($LASTEXITCODE)" }

Write-Host "Done. $tag is the latest release on $Repo." -ForegroundColor Green
