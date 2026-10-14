#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -x .venv-audio/bin/python ]]; then
  echo "[K3-AUDIO] missing .venv-audio; run ./k3_audio_setup.sh first" >&2
  exit 1
fi
if curl -fsS --max-time 2 http://127.0.0.1:18790/healthz >/dev/null 2>&1; then
  echo "[K3-AUDIO] gateway already running"
  exit 0
fi
mkdir -p logs
nohup .venv-audio/bin/python -m uvicorn spacemit_ai_gateway.app.main:app \
  --host 127.0.0.1 --port 18790 \
  > logs/audio-gateway.log 2>&1 < /dev/null &
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:18790/healthz >/dev/null 2>&1; then
    echo "[K3-AUDIO] gateway ready on http://127.0.0.1:18790"
    exit 0
  fi
  sleep 1
done
echo "[K3-AUDIO] gateway did not become ready; inspect logs/audio-gateway.log" >&2
exit 1
