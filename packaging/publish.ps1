# Publish a release and leave only that one on the public repository.
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
    [switch]$KeepOld
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $PSScriptRoot 'out'

$version = (Select-String -Path (Join-Path $root 'Backend\dannify\__init__.py') `
    -Pattern "__version__\s*=\s*'([^']+)'").Matches[0].Groups[1].Value
if (-not $version) { throw 'could not read the version' }

$tag = "v$version"
$files = @(
    (Join-Path $out "Dannify-Setup-$version.exe"),
    (Join-Path $out "manifest-$version.json"),
    (Join-Path $out "files-$version.zip")
)
foreach ($f in $files) { if (-not (Test-Path $f)) { throw "missing $f" } }

Write-Host "Publishing $tag" -ForegroundColor Cyan
& gh release create $tag --repo $Repo --title "Dannify $version" --notes $Notes @files
if ($LASTEXITCODE -ne 0) { throw "gh release create failed ($LASTEXITCODE)" }

if ($KeepOld) { return }

Write-Host 'Removing older releases' -ForegroundColor Cyan
$old = & gh release list --repo $Repo --limit 100 --json tagName --jq '.[].tagName' |
    Where-Object { $_ -and $_ -ne $tag }
foreach ($t in $old) {
    & gh release delete $t --repo $Repo --cleanup-tag --yes
    Write-Host "  removed $t"
}

# The site reads the latest release for its version, date and download link,
# so publishing is all it takes to bring the page up to date.
Write-Host "Done. https://danielmwendwa9451.github.io/dannify-releases/" -ForegroundColor Green
