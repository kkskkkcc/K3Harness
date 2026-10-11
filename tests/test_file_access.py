from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from self_learning_agent.api import app
from self_learning_agent.config import Settings
from self_learning_agent.tools import execute_tool


def file_settings(tmp_path: Path, mode: str = "local") -> Settings:
    return Settings(
        _env_file=None,
        file_access_mode=mode,
        agent_workspace=str(tmp_path / "project" / "workspace"),
        project_root=str(tmp_path / "project"),
    )


async def test_local_mode_reads_and_lists_outside_project(tmp_path: Path) -> None:
    settings = file_settings(tmp_path)
    directory = tmp_path / "outside"
    directory.mkdir()
    document = directory / "中文.txt"
    document.write_text("本机文件读取成功", encoding="gb18030")
    listing = await execute_tool(
        "workspace_list", {"subpath": str(directory)}, settings.agent_workspace,
        settings.project_root, settings,
    )
    assert str(document) in listing
    text = await execute_tool(
        "workspace_read", {"path": str(document)}, settings.agent_workspace,
        settings.project_root, settings,
    )
    assert text == "本机文件读取成功"


async def test_project_mode_still_rejects_external_paths(tmp_path: Path) -> None:
    settings = file_settings(tmp_path, "project")
    with pytest.raises(ValueError, match="escapes the project root"):
        await execute_tool(
            "workspace_read", {"path": str(tmp_path / "outside.txt")},
            settings.agent_workspace, settings.project_root, settings,
        )


async def test_binary_files_are_rejected_and_large_text_is_bounded(tmp_path: Path) -> None:
    settings = file_settings(tmp_path)
    binary = tmp_path / "model.bin"
    binary.write_bytes(b"model\x00data")
    with pytest.raises(ValueError, match="二进制"):
        await execute_tool(
            "workspace_read", {"path": str(binary)}, settings.agent_workspace,
            settings.project_root, settings,
        )
    log = tmp_path / "large.txt"
    log.write_text("a" * 150_000, encoding="utf-8")
    text = await execute_tool(
        "workspace_read", {"path": str(log)}, settings.agent_workspace,
        settings.project_root, settings,
    )
    assert text.startswith("a" * 20_000)
    assert "已截断" in text


def test_api_uses_same_local_permissions_as_agent(tmp_path: Path) -> None:
    settings = file_settings(tmp_path)
    document = tmp_path / "outside.txt"
    document.write_text("API local access works", encoding="utf-8")
    with patch("self_learning_agent.api.get_settings", return_value=settings):
        response = TestClient(app).post(
            "/v1/tools/execute",
            json={"name": "workspace_read", "arguments": {"path": str(document)}},
        )
    assert response.status_code == 200
    assert response.json()["result"] == "API local access works"
