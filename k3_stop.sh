#!/usr/bin/env bash
set -euo pipefail
pkill -f '[u]vicorn self_learning_agent.api:app' 2>/dev/null || true
pkill -f '[l]lama-server --model' 2>/dev/null || true
echo "[K3] Agent and llama-server stopped"
