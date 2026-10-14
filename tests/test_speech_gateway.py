from __future__ import annotations

import httpx

from self_learning_agent.config import Settings
from self_learning_agent.speech_gateway import SpacemiTAIGateway


def _gateway(handler) -> SpacemiTAIGateway:
    settings = Settings(
        _env_file=None,
        audio_enabled=True,
        audio_backend="spacemit_gateway",
        audio_gateway_url="http://audio.test",
    )
    gateway = SpacemiTAIGateway(settings)
    gateway._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://audio.test"
    )
    return gateway


async def test_spacemit_gateway_transcribes_and_synthesizes(tmp_path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/asr/recognize"):
            return httpx.Response(200, json={"text": "找穿红衣服的人"})
        return httpx.Response(
            200,
            content=b"RIFF-test-audio",
            headers={"content-type": "audio/wav"},
        )

    gateway = _gateway(handler)
    source = tmp_path / "input.wav"
    source.write_bytes(b"RIFF-input")
    assert await gateway.transcribe(source) == "找穿红衣服的人"
    output = tmp_path / "reply.wav"
    await gateway.synthesize("我正在识别。", output)
    await gateway.aclose()

    assert output.read_bytes() == b"RIFF-test-audio"
    assert seen == ["/v1/asr/recognize", "/v1/tts/synthesize"]


async def test_gateway_extracts_nested_asr_response(tmp_path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"result": {"transcript": "你好"}}})

    gateway = _gateway(handler)
    source = tmp_path / "input.wav"
    source.write_bytes(b"RIFF-input")
    assert await gateway.transcribe(source) == "你好"
    await gateway.aclose()
