#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "$(uname -m)" != "riscv64" ]]; then
  echo "[K3] warning: current architecture is $(uname -m), expected riscv64"
fi
command -v llama-server >/dev/null 2>&1 || {
  echo "[K3] missing llama-server; install the SpacemiT llama.cpp package first" >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || { echo "[K3] missing python3" >&2; exit 1; }

mkdir -p data workspace cache/tmp models logs
if [[ ! -f .env ]]; then cp .env.k3.example .env; fi

# Prefer a board-native virtualenv. Some Bianbu images omit ensurepip; in that
# case use the system Python with an explicit break-system-packages flag.
VENV_PY=""
if python3 -m venv .venv-k3 >/dev/null 2>&1 && [[ -x .venv-k3/bin/python ]] && .venv-k3/bin/python -m pip --version >/dev/null 2>&1; then
  VENV_PY="$PWD/.venv-k3/bin/python"
fi
if [[ -n "$VENV_PY" ]]; then
  "$VENV_PY" -m pip install --upgrade pip
  "$VENV_PY" -m pip install -r requirements-k1.txt
else
  rm -rf .venv-k3
  python3 -m pip install --break-system-packages --ignore-installed -r requirements-k1.txt
  VENV_PY="$(command -v python3)"
fi
printf '%s\n' "$VENV_PY" > data/python-bin

echo "[K3] setup complete using $VENV_PY"
echo "[K3] edit .env if needed, then run ./k3_start.sh"
