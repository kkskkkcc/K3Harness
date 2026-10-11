from __future__ import annotations

from typing import Any

from self_learning_agent.tools import execute_tool

WORKFLOW_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "project-preflight",
        "name": "项目启动检查",
        "description": "检查本地时间、工作区和硬件网关，不执行物理动作。",
        "steps": [
            {"tool": "get_time", "arguments": {}},
            {"tool": "workspace_list", "arguments": {"subpath": ""}},
            {"tool": "hardware_status", "arguments": {}},
        ],
    },
    {
        "id": "hardware-preflight",
        "name": "硬件安全预检",
        "description": "确认硬件、相机和视觉服务状态；当前只返回模拟状态。",
        "steps": [
            {"tool": "hardware_status", "arguments": {}},
            {"tool": "camera_capture", "arguments": {"camera": "main"}},
        ],
    },
]


async def run_workflow(
    workflow_id: str, workspace: str, project_root: str = ".", settings: Any = None
) -> dict[str, Any]:
    workflow = next((item for item in WORKFLOW_DEFINITIONS if item["id"] == workflow_id), None)
    if workflow is None:
        raise ValueError("工作流不存在")
    results = []
    for step in workflow["steps"]:
        result = await execute_tool(
            step["tool"], step["arguments"], workspace, project_root=project_root, settings=settings
        )
        results.append({"tool": step["tool"], "result": result})
    return {"workflow_id": workflow_id, "name": workflow["name"], "steps": results}
