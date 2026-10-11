param(
  [string]$Python = ""
)
$ErrorActionPreference = "Stop"
$projectRoot = (Get-Location).Path
$env:PIP_CACHE_DIR = Join-Path $projectRoot "cache\pip"
$env:OLLAMA_MODELS = Join-Path $projectRoot "models\ollama"
[Environment]::SetEnvironmentVariable('PIP_CACHE_DIR', $env:PIP_CACHE_DIR, 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $env:OLLAMA_MODELS, 'User')
if (-not $Python) {
  $candidates = @("F:\anaconda\python.exe", "py", "python")
  foreach ($candidate in $candidates) {
    try {
      if ($candidate -eq "py") { & py -3.13 --version *> $null; if ($LASTEXITCODE -eq 0) { $Python = "py -3.13"; break } }
      elseif (Test-Path $candidate) { $Python = $candidate; break }
    } catch {}
  }
}
if (-not $Python) { throw "Python 3.11+ was not found." }
New-Item -ItemType Directory -Force .deps | Out-Null
if ($Python -eq "py -3.13") { & py -3.13 -m pip install --index-url https://pypi.org/simple --target (Resolve-Path .deps) ".[dev]" }
else { & $Python -m pip install --index-url https://pypi.org/simple --target (Resolve-Path .deps) ".[dev]" }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force data,workspace | Out-Null
if ((Test-Path (Join-Path $projectRoot "Qwen3-4B-Q4_K_M.gguf")) -and
    (Test-Path (Join-Path $projectRoot "Qwen3-8B-Q4_K_M.gguf")) -and
    (Test-Path (Join-Path $projectRoot "Qwen3-14B-Q4_K_M.gguf"))) {
  cmd /c (Join-Path $projectRoot "模型导入.bat")
} else {
  Write-Warning "Local Qwen3 GGUF files are incomplete; skipping local model registration."
}
ollama pull nomic-embed-text:latest
Write-Host "Setup complete. Start with .\start.ps1"
