# Builds packaging\media\dnfmedia.exe from source (see build.sh) in a Linux
# container. Needs Docker. The result replaces the media tool the next
# packaging\build.ps1 bundles.
#
#   pwsh -File F:\Projects\Dannify\packaging\mediatool\build-media.ps1
param([string]$FfmpegVersion = '7.1.2')
$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
$media = Join-Path (Split-Path $here -Parent) 'media'
$out = Join-Path $here 'out'
New-Item -ItemType Directory -Force $out | Out-Null
$name = 'dannify-mediatool-build'

# Detached and waited on, rather than attached: an attached run dies with
# the connection to Docker, and a build takes long enough to see one drop.
docker rm -f $name 2>$null | Out-Null
docker run -d --name $name `
    -e FFMPEG_VERSION=$FfmpegVersion `
    -v "${here}:/src:ro" -v "${out}:/out" `
    ubuntu:24.04 bash /src/build.sh | Out-Null
if ($LASTEXITCODE -ne 0) { throw "could not start the build container ($LASTEXITCODE)" }

$code = $null
while ($null -eq $code) {
    $state = docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' $name 2>$null
    if ($state -match '^exited (\d+)') { $code = [int]$Matches[1] } else { Start-Sleep -Seconds 10 }
}
docker logs --tail 40 $name 2>&1
docker rm -f $name | Out-Null
if ($code -ne 0) { throw "media tool build failed ($code)" }

$built = Join-Path $out 'dnfmedia.exe'
if (-not (Test-Path $built)) { throw 'no dnfmedia.exe came out' }
New-Item -ItemType Directory -Force $media | Out-Null
Copy-Item $built (Join-Path $media 'dnfmedia.exe') -Force
"dnfmedia.exe: {0:N1} MB" -f ((Get-Item $built).Length / 1MB)
