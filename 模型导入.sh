#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

for spec in "4b:Qwen3-4B-Q4_K_M.gguf" "8b:Qwen3-8B-Q4_K_M.gguf" "14b:Qwen3-14B-Q4_K_M.gguf"; do
  tag="${spec%%:*}"
  file="${spec#*:}"
  if ! ollama list | awk 'NR > 1 {print $1}' | grep -qx "qwen3-local:${tag}"; then
    echo "[Agent] Importing Qwen3 ${tag}..."
    ollama create "qwen3-local:${tag}" -f "Modelfile-qwen3-${tag}"
  fi
done

echo "[Agent] Local model registration finished."
