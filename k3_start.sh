#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL_TAG="${MODEL_TAG:-4b}"
LLAMA_PORT="${LLAMA_PORT:-8080}"
LLAMA_THREADS="${LLAMA_THREADS:-4}"
LLAMA_CTX_SIZE="${LLAMA_CTX_SIZE:-4096}"
LLAMA_POLL="${LLAMA_POLL:-0}"
START_AGENT="${START_AGENT:-1}"
case "$MODEL_TAG" in
  4b) MODEL_FILE="Qwen3-4B-Q4_K_M.gguf" ;;
  8b) MODEL_FILE="Qwen3-8B-Q4_K_M.gguf" ;;
  14b) MODEL_FILE="Qwen3-14B-Q4_K_M.gguf" ;;
  *) echo "MODEL_TAG must be 4b, 8b or 14b" >&2; exit 2 ;;
esac
MODEL_PATH="$PWD/$MODEL_FILE"
if [[ ! -f "$MODEL_PATH" && -f "$PWD/Qwen3-4B-Q4_K_M.gguf" ]]; then
  echo "[K3] requested $MODEL_TAG model is absent; falling back to 4b"
  MODEL_TAG="4b"
  MODEL_FILE="Qwen3-4B-Q4_K_M.gguf"
  MODEL_PATH="$PWD/$MODEL_FILE"
fi
[[ -f "$MODEL_PATH" ]] || { echo "missing model: $MODEL_PATH" >&2; exit 1; }

mkdir -p data logs workspace
MODEL_READY=0
if curl -fsS "http://127.0.0.1:${LLAMA_PORT}/v1/models" 2>/dev/null | grep -q "qwen3-local:${MODEL_TAG}"; then
  MODEL_READY=1
else
  # A running server with another alias must be replaced when the operator
  # switches 4b/8b/14b; otherwise the API would advertise a model that is not
  # actually loaded.
  pkill -f 'llama-server --model' 2>/dev/null || true
  sleep 2
fi
if [[ "$MODEL_READY" != "1" ]]; then
  echo "[K3] starting llama-server with $MODEL_FILE"
  nohup llama-server \
    --model "$MODEL_PATH" \
    --host 127.0.0.1 \
    --port "$LLAMA_PORT" \
    --alias "qwen3-local:${MODEL_TAG}" \
    --jinja \
    --ctx-size "$LLAMA_CTX_SIZE" \
    --threads "$LLAMA_THREADS" \
    --poll "$LLAMA_POLL" \
    --parallel 1 \
    >"$PWD/logs/llama-server.log" 2>&1 &
  echo $! > "$PWD/data/llama-server.pid"
fi

for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:${LLAMA_PORT}/v1/models" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "http://127.0.0.1:${LLAMA_PORT}/v1/models" >/dev/null 2>&1 || {
  echo "[K3] llama-server did not become ready; inspect logs/llama-server.log" >&2
  exit 1
}

if [[ "$START_AGENT" == "0" ]]; then
  echo "[K3] model $MODEL_TAG is ready; Agent process was not started"
  exit 0
fi

export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"
export AGENT_WORKSPACE="${AGENT_WORKSPACE:-$PWD/workspace}"
export PROJECT_ROOT="${PROJECT_ROOT:-$PWD}"
export FILE_ACCESS_MODE="${FILE_ACCESS_MODE:-local}"
export LLM_BACKEND="${LLM_BACKEND:-openai_compatible}"
export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:${LLAMA_PORT}/v1}"
export OLLAMA_CHAT_MODEL="${OLLAMA_CHAT_MODEL:-qwen3-local:${MODEL_TAG}}"
export OLLAMA_SUMMARY_MODEL="${OLLAMA_SUMMARY_MODEL:-qwen3-local:${MODEL_TAG}}"

PYTHON_BIN="python3"
if [[ -x .venv-k3/bin/python ]]; then PYTHON_BIN=".venv-k3/bin/python"; fi
echo "[K3] starting Agent on http://0.0.0.0:${PORT:-8000} using ${OLLAMA_CHAT_MODEL}"
exec "$PYTHON_BIN" -m uvicorn self_learning_agent.api:app --host 0.0.0.0 --port "${PORT:-8000}"
