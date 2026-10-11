#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "$(uname -m)" != "riscv64" ]]; then
  echo "[K1] warning: current architecture is $(uname -m), expected riscv64"
fi

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  if ! command -v llama-server >/dev/null 2>&1 && ! command -v ollama >/dev/null 2>&1; then
    sudo apt-get install -y llama.cpp-tools-spacemit || sudo apt-get install -y llama-server
  fi
fi

python3 -m venv .venv-k1 2>/dev/null || true
if [[ -x .venv-k1/bin/python ]]; then
  .venv-k1/bin/python -m pip install --upgrade pip
  .venv-k1/bin/python -m pip install -r requirements-k1.txt
else
  python3 -m pip install --user -r requirements-k1.txt
fi

mkdir -p data workspace cache/tmp models
cp -n .env.k1.example .env 2>/dev/null || true
echo "[K1] setup complete; select qwen3-local:4b for the first demo"
