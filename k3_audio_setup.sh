#!/usr/bin/env bash
set -euo pipefail

# Audio dependencies can be prepared and tested with WAV files before a
# microphone or speaker is attached. Keep SDK and caches inside the project.
cd "$(dirname "${BASH_SOURCE[0]}")"
if ! command -v apt-get >/dev/null 2>&1; then
  echo "[K3-AUDIO] apt-get is unavailable; install the SpacemiT audio stack for this image manually." >&2
  exit 1
fi

if ! apt-cache show spacemit-ai-gateway >/dev/null 2>&1; then
  echo "[K3-AUDIO] apt gateway package absent; preparing official Python speech SDK."
  mkdir -p cache/audio-wheels cache/pip
  export PIP_CACHE_DIR="$PWD/cache/pip"
  python3 -m pip download --no-deps --dest cache/audio-wheels \
    --index-url https://git.spacemit.com/api/v4/projects/33/packages/pypi/simple \
    spacemit-asr==1.0.4 spacemit-tts==1.0.4 \
    spacemit-audio==1.0.0 spacemit-vad==1.0.0
  # Use the image's ONNX Runtime/numpy libraries without changing Agent deps.
  python3 -m venv --without-pip --system-site-packages .venv-audio
  python3 -m pip --python .venv-audio/bin/python install --no-deps \
    --no-index --find-links cache/audio-wheels \
    spacemit-ai-gateway==0.2.0 \
    spacemit-asr==1.0.4 spacemit-tts==1.0.4 \
    spacemit-audio==1.0.0 spacemit-vad==1.0.0
  .venv-audio/bin/python -c \
    'import spacemit_asr, spacemit_tts, spacemit_audio, spacemit_vad; print("Speech SDK import OK")'
  cat <<'EOF'
[K3-AUDIO] SDK prepared, but speech models and gateway service are not yet running.
Next: prepare local models and verify ASR/TTS with WAV files before enabling Agent audio.
Keep AUDIO_ENABLED=false until recognition and synthesis pass real tests.
EOF
  exit 0
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
