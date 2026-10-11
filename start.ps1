$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
# Normalise duplicate proxy variables before any subprocess inherits them.
# ``Start-Process`` and ``&`` both clone the current environment; when both
# NO_PROXY and no_proxy (or any case variant of HTTP_PROXY / etc.) are
# present the .NET dictionary throws "Item has already been added" and the
# child process never starts, which silently leaves the old agent running.
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
$env:OLLAMA_MODELS = Join-Path (Get-Location).Path "models\ollama"
$env:PIP_CACHE_DIR = Join-Path (Get-Location).Path "cache\pip"
if (-not (Test-Path .deps)) { throw "Run .\setup.ps1 first." }
New-Item -ItemType Directory -Force data,workspace | Out-Null
$env:PYTHONPATH = (Resolve-Path src).Path + ";" + (Resolve-Path .deps).Path
$env:TEMP = Join-Path $PSScriptRoot 'cache\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
$pythonExe = @((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'), 'F:\anaconda\python.exe') | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $pythonExe) { $pythonExe = (Get-Command python -ErrorAction Stop).Source }
& $pythonExe -m uvicorn self_learning_agent.api:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
