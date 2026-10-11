from __future__ import annotations

from pathlib import Path
from typing import Literal

ModelId = Literal["qwen3-local:4b", "qwen3-local:8b", "qwen3-local:14b"]
ReasoningEffort = Literal["fast", "balanced", "deep"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_PROFILES: dict[str, dict[str, object]] = {
    "qwen3-local:4b": {
        "label": "Qwen3 4B",
        "short_label": "4B",
        "file": "Qwen3-4B-Q4_K_M.gguf",
        "speed": "最快",
        "use_case": "即时回答、轻量工具",
        "ram": "约 4GB",
    },
    "qwen3-local:8b": {
        "label": "Qwen3 8B",
        "short_label": "8B",
        "file": "Qwen3-8B-Q4_K_M.gguf",
        "speed": "平衡",
        "use_case": "日常工作流（推荐）",
        "ram": "约 7GB",
    },
    "qwen3-local:14b": {
        "label": "Qwen3 14B",
        "short_label": "14B",
        "file": "Qwen3-14B-Q4_K_M.gguf",
        "speed": "最强",
        "use_case": "复杂分析、长上下文",
        "ram": "约 12GB",
    },
}

MODEL_ALIASES = {
    "qwen3:4b": "qwen3-local:4b",
    "qwen3:8b": "qwen3-local:8b",
    "qwen3:14b": "qwen3-local:14b",
}

EFFORT_PROFILES: dict[str, dict[str, object]] = {
    "fast": {
        "label": "快速",
        "description": "优先响应速度",
        "max_tokens": 256,
        "max_tool_steps": 2,
        "context_char_budget": 12000,
        "think": False,
    },
    "balanced": {
        "label": "平衡",
        "description": "速度和质量平衡",
        "max_tokens": 512,
        "max_tool_steps": 4,
        "context_char_budget": 18000,
        "think": False,
    },
    "deep": {
        "label": "深度",
        "description": "允许更多推理和工具步骤",
        "max_tokens": 768,
        "max_tool_steps": 6,
        "context_char_budget": 24000,
        "think": True,
    },
}


def canonical_model_id(model: str | None, default: str) -> str:
    candidate = MODEL_ALIASES.get(model or default, model or default)
    return candidate if candidate in MODEL_PROFILES else "qwen3-local:8b"


def list_model_profiles() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for model_id, profile in MODEL_PROFILES.items():
        file_path = PROJECT_ROOT / str(profile["file"])
        result.append(
            {
                "id": model_id,
                **profile,
                "file_available": file_path.exists(),
            }
        )
    return result
