#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
echo "== Agent =="
curl -fsS http://127.0.0.1:${PORT:-8000}/health || true
echo
echo "== Models =="
curl -fsS http://127.0.0.1:${LLAMA_PORT:-8080}/v1/models || true
echo
echo "== Resources =="
free -h
df -h "$PWD"
echo "== Processes =="
ps -eo pid,pcpu,pmem,args | grep -E '[l]lama-server|[u]vicorn self_learning_agent' || true
echo "== Release manifest =="
if [[ -f data/release-manifest.txt ]]; then tail -5 data/release-manifest.txt; else echo "not generated"; fi
