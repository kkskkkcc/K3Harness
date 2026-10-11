# Local model instructions

The Ollama cache and model weights are intentionally excluded from GitHub. Do not copy
large files into this directory and do not commit `models/ollama/`.

Download the selected GGUF file into the **project root**, next to the Modelfiles:

```text
K3Harness/
├── Qwen3-4B-Q4_K_M.gguf
├── Qwen3-8B-Q4_K_M.gguf
└── Qwen3-14B-Q4_K_M.gguf
```

The application uses three project-local Ollama profiles built from those GGUF files:

```powershell
.\模型导入.bat
```

The profiles are `qwen3-local:4b`, `qwen3-local:8b`, and `qwen3-local:14b`. See the
root `README.md` for download links and K3/Linux instructions. The optional embedding
model is `nomic-embed-text:latest` and is pulled by the setup script when available.
