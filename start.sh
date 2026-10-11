#!/usr/bin/env bash
set -euo pipefail
export OLLAMA_MODELS="$PWD/models/ollama"
export PIP_CACHE_DIR="$PWD/cache/pip"
export TMPDIR="$PWD/cache/tmp"
if [ ! -d .deps ]; then
  mkdir -p .deps
  python3 -m pip install --target .deps '.[dev]'
fi
mkdir -p data workspace
if ! curl --fail --silent http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  ollama serve >/dev/null 2>&1 &
  for _ in $(seq 1 30); do curl --fail --silent http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
fi
bash ./模型导入.sh
export PYTHONPATH="$PWD/src:$PWD/.deps"
exec python3 -m uvicorn self_learning_agent.api:app --host 127.0.0.1 --port 8000
