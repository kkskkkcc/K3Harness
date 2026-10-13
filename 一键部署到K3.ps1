param(
    [ValidateSet("4b", "8b", "14b")]
    [string]$ModelTag = "4b",
    [string]$SshHost = "127.0.0.1",
    [int]$SshPort = 2222,
    [string]$RemoteDir = "/root/k3-agent",
    [switch]$SkipModels,
    [switch]$NoStart
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Target = "root@$SshHost"
$ScpArgs = @("-o", "StrictHostKeyChecking=no", "-P", "$SshPort")
$SshArgs = @("-o", "StrictHostKeyChecking=no", "-p", "$SshPort")
$IdentityFile = Join-Path $Root "cache\deploy\k3_deploy_ed25519"
if (Test-Path -LiteralPath $IdentityFile) {
    # The current K3 has this key installed, so repeated deployments do not
    # need the password. A fresh board can still fall back to password auth.
    $ScpArgs += @("-i", $IdentityFile)
    $SshArgs += @("-i", $IdentityFile)
}

Write-Host "[K3] 检查 SSH 隧道 $SshHost`:$SshPort ..." -ForegroundColor Cyan
& ssh @SshArgs $Target "uname -m && test -x /usr/bin/llama-server"
if ($LASTEXITCODE -ne 0) { throw "无法连接 K3 或 K3 缺少 /usr/bin/llama-server" }
& ssh @SshArgs $Target "mkdir -p '$RemoteDir' '$RemoteDir/models' '$RemoteDir/logs' '$RemoteDir/data'"

$Files = @(
    "src", "migrations", "requirements-k1.txt", "pyproject.toml", "README.md",
    ".env.k3.example", "k3_setup.sh", "k3_start.sh", "k3_status.sh", "k3_stop.sh", "K3-部署说明.md",
    "当前进度.md", "总进度.md", "问题.md", "待解决事项.md", "架构与同步.md"
)
foreach ($Item in $Files) {
    $Source = Join-Path $Root $Item
    if (-not (Test-Path -LiteralPath $Source)) { throw "缺少发布文件：$Item" }
    Write-Host "[K3] 复制 $Item" -ForegroundColor DarkCyan
    & scp @ScpArgs -r $Source "${Target}:$RemoteDir/"
    if ($LASTEXITCODE -ne 0) { throw "复制失败：$Item" }
}

if (-not $SkipModels) {
    foreach ($Model in @("Qwen3-4B-Q4_K_M.gguf", "Qwen3-8B-Q4_K_M.gguf", "Qwen3-14B-Q4_K_M.gguf")) {
        $Source = Join-Path $Root $Model
        if (-not (Test-Path -LiteralPath $Source)) { throw "缺少模型文件：$Model" }
        Write-Host "[K3] 复制模型 $Model（大文件，按提示输入 K3 密码）" -ForegroundColor Yellow
        & scp @ScpArgs $Source "${Target}:$RemoteDir/"
        if ($LASTEXITCODE -ne 0) { throw "模型复制失败：$Model" }
    }
}

$RemoteSetup = "cd '$RemoteDir' && find src -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true; chmod +x k3_setup.sh k3_start.sh; if [ ! -f .env ]; then cp .env.k3.example .env; fi; ./k3_setup.sh"
Write-Host "[K3] 安装板端依赖并生成运行目录 ..." -ForegroundColor Cyan
& ssh @SshArgs $Target $RemoteSetup
if ($LASTEXITCODE -ne 0) { throw "K3 环境初始化失败" }

$RemoteManifest = "cd '$RemoteDir' && find src migrations -type f -print0 | sort -z | xargs -0 sha256sum > data/release-manifest.txt; for model in Qwen3-4B-Q4_K_M.gguf Qwen3-8B-Q4_K_M.gguf Qwen3-14B-Q4_K_M.gguf; do [ -f `$model ] && sha256sum `$model >> data/release-manifest.txt; done"
& ssh @SshArgs $Target $RemoteManifest
if ($LASTEXITCODE -ne 0) { throw "生成 K3 版本清单失败" }

if (-not $NoStart) {
    $RemoteStart = "cd '$RemoteDir' && nohup env MODEL_TAG='$ModelTag' ./k3_start.sh > logs/agent.log 2>&1 < /dev/null &"
    Write-Host "[K3] 启动 $ModelTag 模型和 Agent ..." -ForegroundColor Green
    & ssh @SshArgs $Target $RemoteStart
    if ($LASTEXITCODE -ne 0) { throw "K3 启动失败" }
    Write-Host "[K3] 完成。通过 SSH 转发访问 http://127.0.0.1:8000" -ForegroundColor Green
} else {
    Write-Host "[K3] 文件同步完成，按需运行 ./k3_start.sh" -ForegroundColor Green
}
