#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
export PYTHONPATH="$PWD/src:$PWD/.deps:${PYTHONPATH:-}"
export AGENT_WORKSPACE="${AGENT_WORKSPACE:-$PWD/workspace}"
export FILE_ACCESS_MODE="${FILE_ACCESS_MODE:-local}"
export OLLAMA_CHAT_MODEL="${OLLAMA_CHAT_MODEL:-qwen3-local:4b}"
export OLLAMA_SUMMARY_MODEL="${OLLAMA_SUMMARY_MODEL:-qwen3-local:4b}"

PYTHON_BIN="python3"
if [[ -x .venv-k1/bin/python ]]; then PYTHON_BIN=".venv-k1/bin/python"; fi
exec "$PYTHON_BIN" -m uvicorn self_learning_agent.api:app --host 0.0.0.0 --port "${PORT:-8000}"
