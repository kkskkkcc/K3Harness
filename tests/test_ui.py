from fastapi.testclient import TestClient

from self_learning_agent.api import app

# ``TestClient(app, client=(...))`` populates ``request.client.host`` so the
# localhost-only shutdown endpoint can be exercised in unit tests. Production
# never goes through this synthetic address.
client = TestClient(app)


def test_chat_interface_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "K3 Agent · 本地工作台" in response.text
    assert "完成并学习" in response.text


def test_chat_interface_assets_are_served() -> None:
    javascript = client.get("/static/app.js")
    stylesheet = client.get("/static/styles.css")

    assert javascript.status_code == 200
    assert "sendMessage" in javascript.text
    assert stylesheet.status_code == 200
    assert ".chat-column" in stylesheet.text


def test_hardware_gateway_starts_in_safe_simulation_mode() -> None:
    response = client.get("/v1/hardware/status")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["adapter"] == "simulated"


def test_workspace_views_are_real_and_tools_are_exposed() -> None:
    page = client.get("/").text
    assert 'data-view="memory"' in page
    assert 'data-view="tools"' in page
    assert "memory-view" in page
    assert "workflow-grid" in page

    tools = client.get("/v1/tools")
    assert tools.status_code == 200
    assert {item["name"] for item in tools.json()["tools"]} >= {
        "calculator",
        "hardware_status",
    }

    workflow = client.post("/v1/workflows/project-preflight/run")
    assert workflow.status_code == 200
    assert workflow.json()["workflow_id"] == "project-preflight"

    runtime = client.get("/v1/runtime")
    assert runtime.status_code == 200
    assert runtime.json()["memory"]["backend"] == "local"
    assert "embedding_available" in runtime.json()["memory"]


def test_conversations_can_be_listed_and_reopened() -> None:
    conversation = client.post("/v1/conversations", json={"user_id": "ui-test"}).json()
    listed = client.get("/v1/users/ui-test/conversations")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == conversation["id"]
    detail = client.get(f"/v1/conversations/{conversation['id']}")
    assert detail.status_code == 200
    assert detail.json()["messages"] == []


def test_shutdown_endpoint_responds_for_localhost_caller() -> None:
    # The endpoint accepts only localhost callers. TestClient normally does
    # not populate ``request.client.host``; passing ``client=(...)`` here
    # makes the synthetic request look like a real localhost caller.
    local_client = TestClient(app, client=("127.0.0.1", 50000))
    response = local_client.post("/v1/shutdown")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "shutting_down"
    assert "message" in payload


def test_shutdown_endpoint_rejects_non_localhost_caller() -> None:
    # A remote caller must not be able to kill the local Agent. TestClient
    # supports the same ``client=`` tuple to simulate a remote address.
    remote_client = TestClient(app, client=("203.0.113.5", 50000))
    response = remote_client.post("/v1/shutdown")
    assert response.status_code == 403
