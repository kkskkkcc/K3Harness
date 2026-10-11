# Portable Local Agent (Qwen3 + Memory + Tools)

This deployment is based on [Dilep01/self-learning-ai-agent](https://github.com/Dilep01/self-learning-ai-agent) and is prepared as a self-contained local-first agent for later transfer to the K3COM260 board.

It provides:

- Ollama chat and structured conversation summarization
- durable user memory with source-message provenance
- SQLite persistence that can be copied with the project
- context budgeting and bounded recent-history retrieval
- safe tools: workspace listing/reading, calculator, and local time
- FastAPI API plus a small browser UI
- Chinese UI with an external-network switch that is off by default
- opt-in DuckDuckGo HTML search only when the user confirms the switch
- Codex-style three-column workspace with model and reasoning controls
- hardware gateway boundary for future K3 actuators, cameras, and YOLO vision
- optional Mem0/Qdrant/PostgreSQL mode for a larger server

## Model note

模型权重没有提交到 GitHub。仓库只保留 Modelfile、导入脚本和使用说明；下载后的模型必须放在**项目根目录**，与 `Modelfile-qwen3-*.gguf` 同级：

```text
K3Harness/
├── Qwen3-4B-Q4_K_M.gguf
├── Qwen3-8B-Q4_K_M.gguf
└── Qwen3-14B-Q4_K_M.gguf
```

可按需下载以下模型（不需要全部下载）：

| 模型 | 下载地址 | 建议用途 |
| --- | --- | --- |
| Qwen3 4B | [SpacemiT Model Zoo](https://archive.spacemit.com/spacemit-ai/model_zoo/llm/Qwen3-4B-Q4_K_M.gguf) | 低内存、快速响应 |
| Qwen3 8B | [SpacemiT Model Zoo](https://archive.spacemit.com/spacemit-ai/model_zoo/llm/Qwen3-8B-Q4_K_M.gguf) | 默认平衡档 |
| Qwen3 14B | [ModelScope](https://modelscope.cn/models/unsloth/Qwen3-14B-GGUF/resolve/master/Qwen3-14B-Q4_K_M.gguf) | 更复杂的规划和分析 |

Windows 可以直接使用 `模型下载bat/8b.txt` 或 `模型下载bat/14b+4b.txt` 中的命令；下载后请把文件移动到项目根目录。Linux/K3 也必须把文件放在项目根目录，再运行 `./模型导入.sh`。

模型文件通常为数 GB，GitHub 仓库不会包含这些文件。模型导入后，脚本会在本机 Ollama 中创建：`qwen3-local:4b`、`qwen3-local:8b` 和 `qwen3-local:14b`。

## Local prerequisites

- Windows/Linux with Python 3.11+ (the current machine has Anaconda Python 3.13 at `F:\anaconda\python.exe`)
- Ollama 0.31+ and enough memory for the selected model
- Docker is optional; the default profile does not use it

Run the one-time setup in PowerShell:

```powershell
.\setup.ps1
```

The script installs the Python packages into the project-local `.deps` directory, creates local data folders, registers the local Qwen3 profiles, and pulls only the embedding model:

```text
nomic-embed-text:latest
```

The three downloaded GGUF files are exposed as local Ollama profiles by `模型导入.bat`:

| UI档位 | Ollama 名称 | 用途 |
| --- | --- | --- |
| 快速 | `qwen3-local:4b` | 即时回答、轻量工具 |
| 平衡（默认） | `qwen3-local:8b` | 日常任务和 K3 迁移 |
| 深度 | `qwen3-local:14b` | 复杂分析、更多工具步骤 |

The “调用强度” control changes generation limits, context budget, tool-call steps, and Qwen3 thinking mode. Fast and balanced keep thinking disabled for lower latency; deep enables it when `OLLAMA_DISABLE_THINKING=false`.

## K3 硬件扩展边界

当前版本还没有连接真实机械臂、执行器或摄像头，也不会执行任何物理动作。`src/self_learning_agent/hardware_gateway.py` 已提供独立的 Hardware Gateway 接口和安全模拟适配器；`/v1/hardware/status` 会明确返回当前是模拟模式。迁移到 K3 后，可以在这个边界内加入 GPIO、串口、CAN、相机和 YOLO 驱动，再把硬件动作注册为带权限和超时的 Agent 工具。这样自然语言对话只负责提出意图，工作流层负责审批和编排，硬件网关负责最后的设备执行。

Start the agent:

```powershell
.\start.ps1
```

Then open <http://127.0.0.1:8000> or the API docs at <http://127.0.0.1:8000/docs>.
On Windows, double-click `一键启动.bat`; it starts the service, waits for `/health`, and opens the web interface automatically.

## 本机文件访问

当前 `.env` 设置 `FILE_ACCESS_MODE=local`。Agent 可以通过 `workspace_list`
浏览本机目录、通过 `workspace_read` 读取文本文件，支持项目外的绝对路径，
例如聊天输入“列出 D:\\mc 目录中的文件”。相对路径仍以 `AGENT_WORKSPACE` 为基准。
访问权限与运行服务的系统账户相同，不要求把文件复制到项目目录。
网页右侧显示“本机文件可读”，工具测试台也可以直接测试目录和文件。
本次提供目录浏览和文本读取；文本编码支持 UTF-8、UTF-16 BOM、GB18030。
这两个工具不负责解析图片、PDF 或 Office 文档。
大目录和文件会截断返回内容，避免读取模型文件或日志时耗尽内存。
如需恢复项目范围限制，将配置改为 `FILE_ACCESS_MODE=project` 后重启服务。
迁移到 K3/Linux 后可直接使用 `/home/...` 等路径，无需修改工具代码。

## 外网使用

网页右上角的“外网：关闭”按钮默认关闭。点击开启时会先弹出警告；只有用户确认后，发送的消息才会请求外部搜索服务，并把搜索结果作为不可信上下文交给 Agent。关闭后不会主动连接外网。API 调用也可以显式传入 `{"use_web":true}`，省略该字段或传入 `false` 都保持本地模式。

## API quick test

```powershell
$c = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/conversations `
  -ContentType application/json -Body '{"user_id":"demo"}'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/conversations/$($c.id)/messages" `
  -ContentType application/json -Body '{"content":"My name is Alex and I prefer concise answers."}'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/conversations/$($c.id)/finalize"
Invoke-RestMethod http://127.0.0.1:8000/v1/users/demo/memories
```

The agent only writes long-term memories after finalization. Retrieved memories are passed as untrusted context, and tool access is limited to the configured `workspace` directory.

## 工作台功能

左侧导航现在对应真实功能：对话页会加载并恢复本地任务历史；记忆页可以查看和删除已验证的长期记忆；工具与工作流页会读取实际工具目录、显示硬件网关状态、测试安全工具，并运行项目启动检查和硬件安全预检。当前硬件工作流只读状态，任何真实执行器动作仍会被模拟网关拒绝。

## Transfer to K3COM260

将仓库复制到 K3 后，先按照上面的说明把至少一个 GGUF 模型下载到**项目根目录**，再安装 Python 3.11+、ARM64 Ollama 和项目依赖，运行 `./模型导入.sh`，最后运行 `./start.sh`。模型不会随 Git 克隆自动出现，也不会从 GitHub 自动下载。

如果 K3 内存较小，优先使用 4B 或 8B；模型加载后可以在网页工作台中自由切换已导入的模型和调用强度。`data/`、`workspace/`、`.env` 和 Ollama 缓存属于本地运行文件，不提交到仓库。

The default SQLite file is `data/agent.db`; it contains conversations, summaries, and local memories and is portable across operating systems. Keep a backup before moving it while the service is running.

## Optional production profile

The original `compose.yaml` remains available for a server with Docker, PostgreSQL, Qdrant, and Mem0. To use it, set `MEMORY_BACKEND=mem0` and provide the PostgreSQL/Qdrant services. The portable local profile is the recommended path for K3.

## Validation

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD\.deps"
F:\anaconda\python.exe -m pytest
.\.deps\bin\ruff.exe check src tests
```
