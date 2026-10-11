from types import SimpleNamespace

from self_learning_agent.config import Settings
from self_learning_agent.llm import OllamaLLMGateway, parse_conversation_summary


class FakeOllamaClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(message=SimpleNamespace(content=self.content))


async def test_answer_uses_native_non_thinking_ollama_request() -> None:
    gateway = OllamaLLMGateway(Settings(_env_file=None))
    client = FakeOllamaClient("READY")
    gateway._client = client

    answer = await gateway.answer("Are you ready?", [], [])

    assert answer == "READY"
    assert client.calls[0]["model"] == "qwen3-local:8b"
    assert client.calls[0]["think"] is False
    assert client.calls[0]["options"]["num_predict"] == 512
    assert client.calls[0]["keep_alive"] == "2m"


async def test_answer_deep_effort_uses_selected_model_and_more_tokens() -> None:
    gateway = OllamaLLMGateway(Settings(_env_file=None))
    client = FakeOllamaClient("READY")
    gateway._client = client

    await gateway.answer(
        "Think carefully", [], [], model="qwen3-local:14b", reasoning_effort="deep"
    )

    assert client.calls[0]["model"] == "qwen3-local:14b"
    assert client.calls[0]["think"] is True
    assert client.calls[0]["options"]["num_predict"] == 768


def test_summary_parser_accepts_small_model_wrapper() -> None:
    summary = parse_conversation_summary(
        '{"conversation_summary":{"synopsis":"A short conversation."}}'
    )

    assert summary.synopsis == "A short conversation."
