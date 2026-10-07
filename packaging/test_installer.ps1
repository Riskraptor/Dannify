# Checks the installer program reads its payload whether or not the setup
# is code-signed, and that the launcher it leaves behind is the plain engine.
#
#   pwsh packaging\test_installer.ps1
#
# Builds the installer program, packs a small stand-in app onto it, and then,
# unsigned and signed with a throwaway self-signed certificate:
#   --verify-payload   unpacks and hashes every file (exit 0)
#   --write-engine     the launcher copy must be byte-identical to the engine
# The certificate is created in CurrentUser\My and always removed again.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'Backend\venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }
$csproj = Join-Path $root 'installer\Dannify.Setup.csproj'
$engine = Join-Path $root 'installer\bin\Release\DannifySetup.exe'

& dotnet build $csproj -c Release -nologo -v q
if ($LASTEXITCODE -ne 0) { throw "installer build failed ($LASTEXITCODE)" }

$work = Join-Path ([IO.Path]::GetTempPath()) ('dannify-installer-test-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
$failed = 0
$cert = $null
try {
    New-Item -ItemType Directory (Join-Path $work 'app\runtime') | Out-Null
    Set-Content (Join-Path $work 'app\Dannify.exe') 'stand-in app'
    [IO.File]::WriteAllBytes((Join-Path $work 'app\runtime\blob.bin'), [byte[]](1..255 * 400))
    $setup = Join-Path $work 'Setup.exe'
    & $python (Join-Path $PSScriptRoot 'make_setup.py') (Join-Path $work 'app') 0.0.1 $engine $setup | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "packing failed ($LASTEXITCODE)" }
    $engineHash = (Get-FileHash $engine).Hash

    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=Dannify installer test' -CertStoreLocation Cert:\CurrentUser\My
    foreach ($case in 'unsigned', 'signed') {
        $file = Join-Path $work "$case.exe"
        Copy-Item $setup $file
        if ($case -eq 'signed') {
            # Untrusted (self-signed) is fine: only the layout signing leaves matters.
            Set-AuthenticodeSignature -FilePath $file -Certificate $cert -HashAlgorithm SHA256 | Out-Null
            if ((Get-Item $file).Length -le (Get-Item $setup).Length) { throw 'signing did not add a signature' }
        }
        $verify = Start-Process $file -ArgumentList @('--verify-payload', '--data', (Join-Path $work "v-$case")) -Wait -PassThru
        $launcher = Join-Path $work "launcher-$case.exe"
        $write = Start-Process $file -ArgumentList @('--write-engine', $launcher, '--data', (Join-Path $work "w-$case")) -Wait -PassThru
        $same = (Test-Path $launcher) -and ((Get-FileHash $launcher).Hash -eq $engineHash)
        $ok = $verify.ExitCode -eq 0 -and $write.ExitCode -eq 0 -and $same
        if (-not $ok) { $failed++ }
        Write-Host ("  {0,-9} verify={1} launcher={2} identical={3}  {4}" -f $case, $verify.ExitCode, $write.ExitCode, $same, $(if ($ok) { 'OK' } else { 'FAILED' }))
    }
} finally {
    if ($cert) { Remove-Item -Path ('Cert:\CurrentUser\My\' + $cert.Thumbprint) -Force -ErrorAction SilentlyContinue }
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
if ($failed) { throw "$failed installer check(s) failed" }
Write-Host 'Installer checks passed.' -ForegroundColor Green
