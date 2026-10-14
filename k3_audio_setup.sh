#!/usr/bin/env bash
set -euo pipefail

# Optional K3 audio preparation.  It intentionally is not called by
# k3_setup.sh: the package needs the board's microphone/speaker wiring and
# may pull SpacemiT's model wheels from its package registry.
if ! command -v apt-get >/dev/null 2>&1; then
  echo "[K3-AUDIO] apt-get is unavailable; install the SpacemiT audio stack for this image manually." >&2
  exit 1
fi

if ! apt-cache show spacemit-ai-gateway >/dev/null 2>&1; then
  cat >&2 <<'EOF'
[K3-AUDIO] spacemit-ai-gateway is not present in the configured apt sources.
Install/enable the SpacemiT repository first, then rerun this script.
The Agent remains safe with AUDIO_ENABLED=false until the package is ready.
EOF
  exit 2
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  spacemit-ai-gateway \
  opencv-spacemit \
  espeak-ng \
  python3-spacemit-ort \
  spacemit-onnxruntime

systemctl enable --now spacemit-ai-gateway
systemctl --no-pager --full status spacemit-ai-gateway || true
echo "[K3-AUDIO] gateway should now listen on http://127.0.0.1:18790"
echo "[K3-AUDIO] set AUDIO_ENABLED=true and AUDIO_BACKEND=spacemit_gateway in /root/k3-agent/.env after microphone/speaker checks"
