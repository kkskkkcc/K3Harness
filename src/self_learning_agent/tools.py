from __future__ import annotations

import ast
import asyncio
import json
import logging
import operator
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EXPLICIT_PATH_RE = re.compile(
    r"(?<![\w:])(\/(?:[^\s，。；！？,!?]+)|[A-Za-z]:\\[^\s，。；！？,!?]+)"
)


def extract_explicit_path(question: str) -> str | None:
    """Extract a likely absolute local path from a direct file request."""
    match = _EXPLICIT_PATH_RE.search(question)
    if not match:
        return None
    return match.group(1).rstrip(".)]}>。，；！？")


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "workspace_list",
            "description": (
                "List local files and folders. Use subpath for an absolute local path "
                "(for example D:\\mc or /home/user), or a path relative to the workspace. "
                "Local mode allows paths outside the project; project mode limits access "
                "to the project root. Follow filesystem_access in the request."
            ),
            "parameters": {"type": "object", "properties": {"subpath": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_read",
            "description": (
                "Read a local text file using an absolute path or a workspace-relative "
                "path. Supports UTF-8, UTF-16 BOM and Chinese GB18030. Local mode permits "
                "files outside the project, subject to operating system permissions. "
                "This reads text; it does not interpret PDFs, images or office documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a basic arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current local time.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hardware_status",
            "description": (
                "Read the safe status of the K3 hardware gateway, cameras, actuators, "
                "and vision backend. On K3 this returns live driver info; on the "
                "developer machine it returns the safe simulation report."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "camera_capture",
            "description": (
                "Request a camera frame through the hardware gateway. Returns a base64 "
                "JPEG once a real camera driver is installed; otherwise returns the "
                "safe simulation report."
            ),
            "parameters": {
                "type": "object",
                "properties": {"camera": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hardware_command",
            "description": (
                "Request an actuator or robot command. The gateway must approve it; "
                "the gateway in simulation mode rejects everything and the on-K3 "
                "gateway enforces workspace bounds and timeout."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string"},
                    "action": {"type": "string"},
                    "parameters": {"type": "object"},
                },
                "required": ["device", "action"],
            },
        },
    },
]


def select_tool_schemas(question: str) -> list[dict[str, Any]]:
    """Keep the model prompt small by exposing only relevant tools.

    The K3 CPU spends most of its time pre-filling the prompt. Sending every
    hardware, camera, calculator and filesystem schema for a greeting made
    even trivial requests pay the full tool-context cost. The selection is a
    conservative keyword gate; file and hardware requests retain their real
    tools, while ordinary conversation receives no tool schema.
    """
    text = question.casefold()
    names: set[str] = set()
    file_markers = (
        "文件", "文件夹", "目录", "读取", "读一下", "查看", "内容", "路径",
        "workspace", "/", "\\", ".md", ".txt", ".json", ".py", ".yaml",
    )
    if any(marker in text for marker in file_markers):
        names.update({"workspace_list", "workspace_read"})
    if any(marker in text for marker in ("时间", "几点", "日期", "today", "date", "time")):
        names.add("get_time")
    if any(marker in text for marker in ("计算", "算一下", "等于", "calculate")):
        names.add("calculator")
    if any(marker in text for marker in ("机械臂", "摄像头", "相机", "执行器", "硬件", "yolo")):
        names.update({"hardware_status", "camera_capture", "hardware_command"})
    return [schema for schema in TOOL_SCHEMAS if schema["function"]["name"] in names]


def _safe_path(
    root: Path, requested: str, project_root: Path | None = None, *, allow_local: bool = False
) -> Path:
    """Resolve paths in local mode or enforce the project boundary in project mode."""
    workspace_root = root.resolve()
    path = Path(os.path.expandvars(requested.strip().strip('"'))).expanduser()
    if path.drive and not path.is_absolute():
        raise ValueError("请使用完整绝对路径，例如 D:\\mc，而不是 D:mc")
    candidate = (workspace_root / path).resolve()
    if allow_local:
        return candidate
    if (
        workspace_root not in candidate.parents
        and candidate != workspace_root
    ):
        if project_root is None:
            raise ValueError("path escapes the agent workspace")
        project_root_resolved = project_root.resolve()
        if (
            project_root_resolved not in candidate.parents
            and candidate != project_root_resolved
        ):
            raise ValueError("path escapes the project root")
    return candidate


def _list_files(directory: Path) -> str:
    if not directory.is_dir():
        raise ValueError(f"目录不存在：{directory}")
    items: list[str] = []
    with os.scandir(directory) as entries:
        for entry in entries:
            if len(items) >= 250:
                items.append("[目录较大，仅显示前250项]")
                break
            kind = "目录" if entry.is_dir(follow_symlinks=False) else "文件"
            items.append(f"[{kind}] {entry.path}")
    return f"目录：{directory}\n" + ("\n".join(items) if items else "[空目录]")


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"文件不存在：{path}")
    # Read a bounded prefix even for large model files or logs.
    with path.open("rb") as stream:
        raw = stream.read(128_001)
    truncated = len(raw) > 128_000
    raw = raw[:128_000]
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    else:
        if b"\x00" in raw:
            raise ValueError("这是二进制文件，请使用对应的文档、图片或模型处理工具")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    "文件编码无法识别，当前支持 UTF-8、UTF-16 BOM、GB18030 文本"
                ) from exc
    if len(text) > 20_000:
        truncated = True
    return text[:20_000] + ("\n[文件内容已截断]" if truncated else "")


def _calculate(expression: str) -> float | int:
    allowed = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def visit(node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed:
            return allowed[type(node.op)](visit(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in allowed:
            return allowed[type(node.op)](visit(node.left), visit(node.right))
        raise ValueError("only basic arithmetic is allowed")

    return visit(ast.parse(expression, mode="eval").body)


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    workspace: str,
    project_root: str = ".",
    settings: Any = None,
) -> str:
    root = Path(workspace).resolve()  # noqa: ASYNC240
    root.mkdir(parents=True, exist_ok=True)
    project = Path(project_root).resolve() if project_root else None  # noqa: ASYNC240
    allow_local = getattr(settings, "file_access_mode", "project") == "local"
    if name == "get_time":
        return datetime.now().astimezone().isoformat()
    if name in {"hardware_status", "camera_capture", "hardware_command"}:
        return await _run_hardware_tool(name, arguments, settings)
    if name == "calculator":
        return str(_calculate(str(arguments.get("expression", ""))))
    if name == "workspace_list":
        directory = _safe_path(
            root, str(arguments.get("subpath", arguments.get("path", ""))),
            project_root=project, allow_local=allow_local,
        )
        return await asyncio.to_thread(_list_files, directory)
    if name == "workspace_read":
        path = _safe_path(
            root, str(arguments.get("path", "")), project_root=project, allow_local=allow_local
        )
        return await asyncio.to_thread(_read_text, path)
    raise ValueError(f"unknown tool: {name}")


async def _run_hardware_tool(
    name: str, arguments: dict[str, Any], settings: Any
) -> str:
    """Route hardware_* tools through the configured HardwareKernel.

    Importing the kernel here (rather than at module load) avoids forcing
    every test to construct a settings object — tests simply pass
    ``settings=None`` and get the safe simulation report.
    """
    from self_learning_agent.hardware_gateway import build_hardware_kernel

    kernel = build_hardware_kernel(settings) if settings is not None else None
    if kernel is None:
        # No settings → render a static fallback so unit tests stay useful
        # without instantiating a full Settings object.
        if name == "hardware_status":
            return (
                "硬件网关处于安全模拟模式；尚未连接机械臂、摄像头、执行器或 YOLO。"
            )
        if name == "camera_capture":
            return "摄像头驱动尚未连接，未采集图像。"
        return "硬件控制尚未启用，未执行任何物理动作。"
    if name == "hardware_status":
        payload = await kernel.status()
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if name == "camera_capture":
        payload = await kernel.capture(camera=str(arguments.get("camera", "main")))
        return json.dumps(payload, ensure_ascii=False, indent=2)
    # hardware_command
    payload = await kernel.command(
        device=str(arguments.get("device", "")),
        action=str(arguments.get("action", "")),
        parameters=dict(arguments.get("parameters") or {}),
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)
