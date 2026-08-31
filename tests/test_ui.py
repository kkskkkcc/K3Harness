from fastapi.testclient import TestClient

from self_learning_agent.api import app

client = TestClient(app)


def test_chat_interface_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Recall — Local AI Memory Workbench" in response.text
    assert "Finalize &amp; learn" in response.text


def test_chat_interface_assets_are_served() -> None:
    javascript = client.get("/static/app.js")
    stylesheet = client.get("/static/styles.css")

    assert javascript.status_code == 200
    assert "sendMessage" in javascript.text
    assert stylesheet.status_code == 200
    assert ".chat-workspace" in stylesheet.text
