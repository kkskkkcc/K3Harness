$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:OLLAMA_MODELS = Join-Path $PSScriptRoot 'models\ollama'
$env:TEMP = Join-Path $PSScriptRoot 'cache\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:OLLAMA_MODELS,$env:TEMP | Out-Null
$ollamaExe = (Get-Command ollama -ErrorAction Stop).Source
function Test-Ollama {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
        return $true
    } catch { return $false }
}
if (-not (Test-Ollama)) {
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'data\ollama.log') -RedirectStandardError (Join-Path $PSScriptRoot 'data\ollama-error.log')
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Ollama) { break }
        Start-Sleep -Seconds 1
    }
}
if (-not (Test-Ollama)) { throw 'Ollama failed to start. Check data\ollama-error.log.' }
foreach ($tag in @('4b','8b','14b')) {
    $models = (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5).models
    if ($models.name -contains "qwen3-local:$tag") { continue }
    $modelfile = Join-Path $PSScriptRoot "Modelfile-qwen3-$tag"
    if (-not (Test-Path -LiteralPath $modelfile)) {
        Write-Host "[Agent] Skip Qwen3 ${tag}: Modelfile not included (optional placeholder)."
        continue
    }
    $fromLine = Get-Content -LiteralPath $modelfile | Where-Object { $_ -match '^FROM\s+(.+)$' } | Select-Object -First 1
    $fromRelative = if ($fromLine) { ($fromLine -replace '^FROM\s+', '').Trim() } else { '' }
    $fromRelative = $fromRelative.TrimStart('./')
    if ($fromRelative -and -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $fromRelative))) {
        Write-Host "[Agent] Skip Qwen3 ${tag}: GGUF not included (optional placeholder)."
        continue
    }
    Write-Host "[Agent] Importing Qwen3 $tag from local GGUF. This can take several minutes."
    & $ollamaExe create "qwen3-local:$tag" -f $modelfile
    if ($LASTEXITCODE -ne 0) { throw "Model import failed: $tag. No model will be downloaded." }
}
# Ensure the embedding model is registered so semantic memory can start
# working instead of silently falling back to lexical matching. ``pull`` is
# idempotent: it reuses the cached blob when the model is already present.
$embeddingModel = 'nomic-embed-text:latest'
$registered = (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5).models.name
if ($registered -notcontains $embeddingModel) {
    Write-Host "[Agent] Pulling $embeddingModel for semantic memory. This is a one-time download."
    & $ollamaExe pull "$embeddingModel"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "[Agent] Failed to pull $embeddingModel; long-term memory will use lexical fallback."
    }
}
Write-Host '[Agent] All local models are ready.'
