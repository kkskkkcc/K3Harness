from __future__ import annotations

import json

import httpx

from self_learning_agent.config import Settings
from self_learning_agent.llm import OpenAICompatibleLLMGateway


def _gateway(handler) -> OpenAICompatibleLLMGateway:
    settings = Settings(
        _env_file=None,
        llm_backend="openai_compatible",
        llm_base_url="http://test/v1",
        ollama_disable_thinking=True,
    )
    gateway = OpenAICompatibleLLMGateway(settings)
    gateway._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test/v1"
    )
    return gateway


async def test_openai_gateway_sends_qwen3_no_thinking_extension() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "READY"}}
                ]
            },
        )

    answer = await _gateway(handler).answer(
        "Are you ready?", [], [], model="qwen3-local:4b", reasoning_effort="fast"
    )

    assert answer == "READY"
    assert requests[0]["model"] == "qwen3-local:4b"
    assert requests[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "tools" not in requests[0]


async def test_openai_gateway_sends_only_filesystem_tools_for_file_question() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "READY"}}]},
        )

    await _gateway(handler).answer("请读取 /root/k3-agent/README.md", [], [])
    names = {
        item["function"]["name"]
        for item in requests[0]["tools"]
    }
    assert names == {"workspace_list", "workspace_read"}


async def test_openai_gateway_parses_json_summary() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "synopsis": "测试",
                                    "user_goals": [],
                                    "preferences": [],
                                    "candidate_memories": [],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    }
                ]
            },
        )

    summary = await _gateway(handler).summarize([])
    assert summary.synopsis == "测试"
