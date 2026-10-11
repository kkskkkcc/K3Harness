$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
New-Item -ItemType Directory -Force data,cache\tmp | Out-Null
$env:TEMP = Join-Path $PSScriptRoot 'cache\tmp'
$env:TMP = $env:TEMP
# Normalise duplicate proxy variables before Start-Process clones them.
# Windows PowerShell's Start-Process fails with "Item has already been added"
# when both NO_PROXY and no_proxy (or any case variant of HTTP_PROXY / etc.)
# are present, because the underlying .NET dictionary is case-insensitive.
foreach ($pair in @(
    @{ Name = 'NO_PROXY'; Aliases = @('no_proxy') },
    @{ Name = 'HTTP_PROXY'; Aliases = @('http_proxy') },
    @{ Name = 'HTTPS_PROXY'; Aliases = @('https_proxy') }
)) {
    $primary = [Environment]::GetEnvironmentVariable($pair.Name)
    foreach ($alias in $pair.Aliases) {
        [Environment]::SetEnvironmentVariable($alias, $null)
    }
    if ($primary) {
        [Environment]::SetEnvironmentVariable($pair.Name, $primary)
    }
}
if (-not (Test-Path '.deps\fastapi')) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed.' }
}
& (Join-Path $PSScriptRoot 'import-models.ps1')
function Test-Agent {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2
        return $true
    } catch { return $false }
}
if (-not (Test-Agent)) {
    Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'start.ps1') + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'data\agent.log') -RedirectStandardError (Join-Path $PSScriptRoot 'data\agent-error.log')
}
for ($i = 0; $i -lt 60; $i++) {
    if (Test-Agent) {
        Start-Process 'http://127.0.0.1:8000'
        Write-Host '[Agent] Ready. Web interface opened.'
        exit 0
    }
    Start-Sleep -Seconds 1
}
throw 'Agent failed to start. Check data\agent-error.log.'
