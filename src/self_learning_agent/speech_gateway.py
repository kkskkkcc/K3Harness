"""Speech I/O boundary for the Agent.

The K3 deployment uses SpacemiT's official AI Gateway for audio capture,
ASR, VAD and TTS.  Keeping this adapter HTTP-based lets the Agent run with
audio disabled on Windows/K1 while the board-side audio implementation is
installed later, without importing RISC-V-only wheels into the project.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Protocol

import httpx

from self_learning_agent.config import Settings


class AudioGatewayError(RuntimeError):
    """A user-facing audio backend failure."""


class AudioGateway(Protocol):
    async def aclose(self) -> None: ...

    async def status(self) -> dict[str, Any]: ...

    async def transcribe(self, audio_path: Path) -> str: ...

    async def synthesize(self, text: str, output_path: Path) -> Path: ...


class DisabledAudioGateway:
    async def aclose(self) -> None:
        return None

    async def status(self) -> dict[str, Any]:
        return {
            "enabled": False,
            "backend": "disabled",
            "asr": {"available": False},
            "tts": {"available": False},
            "message": "语音模块尚未启用；等待 K3 接入麦克风、音响和 SpacemiT AI Gateway。",
        }

    async def transcribe(self, audio_path: Path) -> str:  # noqa: ARG002
        raise AudioGatewayError("语音输入未启用，请先在 K3 安装并启用 SpacemiT AI Gateway。")

    async def synthesize(self, text: str, output_path: Path) -> Path:  # noqa: ARG002
        raise AudioGatewayError("语音输出未启用，请先在 K3 安装并启用 SpacemiT AI Gateway。")


class SpacemiTAIGateway:
    """Adapter for the official SpacemiT AI Gateway HTTP API."""

    def __init__(self, settings: Settings) -> None:
        headers = {"X-API-Key": settings.audio_api_key} if settings.audio_api_key else {}
        self._client = httpx.AsyncClient(
            base_url=settings.audio_gateway_url.rstrip("/"),
            headers=headers,
            trust_env=False,
            timeout=120.0,
        )
        self._asr_model = settings.audio_asr_model
        self._tts_model = settings.audio_tts_model

    async def aclose(self) -> None:
        await self._client.aclose()

    async def status(self) -> dict[str, Any]:
        try:
            response = await self._client.get("/healthz", timeout=3.0)
            response.raise_for_status()
            return {
                "enabled": True,
                "backend": "spacemit_gateway",
                "asr": {"available": True, "model": self._asr_model},
                "tts": {"available": True, "model": self._tts_model},
                "gateway": response.json() if response.content else {},
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "enabled": True,
                "backend": "spacemit_gateway",
                "asr": {"available": False, "model": self._asr_model},
                "tts": {"available": False, "model": self._tts_model},
                "message": f"无法连接 SpacemiT AI Gateway：{exc}",
            }

    async def transcribe(self, audio_path: Path) -> str:
        try:
            with audio_path.open("rb") as stream:
                response = await self._client.post(
                    "/v1/asr/recognize",
                    files={"file": (audio_path.name, stream, "audio/wav")},
                    data={"model": self._asr_model},
                )
            response.raise_for_status()
            payload = response.json()
        except (OSError, httpx.HTTPError, ValueError) as exc:
            raise AudioGatewayError(f"ASR 语音识别失败：{exc}") from exc
        text = _extract_text(payload)
        if not text:
            raise AudioGatewayError("ASR 返回了空文本，请检查麦克风、音频格式或说话时长。")
        return text

    async def synthesize(self, text: str, output_path: Path) -> Path:
        try:
            response = await self._client.post(
                "/v1/tts/synthesize",
                json={"text": text, "model": self._tts_model},
            )
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                payload = response.json()
                encoded = payload.get("audio") or payload.get("data")
                if not isinstance(encoded, str):
                    raise AudioGatewayError("TTS 返回 JSON，但没有 audio/data 音频字段。")
                output_path.write_bytes(base64.b64decode(encoded))
            else:
                output_path.write_bytes(response.content)
        except AudioGatewayError:
            raise
        except (OSError, httpx.HTTPError, ValueError, base64.binascii.Error) as exc:
            raise AudioGatewayError(f"TTS 语音合成失败：{exc}") from exc
        return output_path


def _extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("text", "transcript", "transcription"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("result", "data"):
        nested = payload.get(key)
        text = _extract_text(nested)
        if text:
            return text
    return ""


def build_audio_gateway(settings: Settings) -> AudioGateway:
    if settings.audio_enabled and settings.audio_backend == "spacemit_gateway":
        return SpacemiTAIGateway(settings)
    return DisabledAudioGateway()
