from fastapi.testclient import TestClient
from app.main import app
import os

client = TestClient(app)


def test_chat_placeholder(monkeypatch):
    # Ensure OPENAI_API_KEY is not set
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = client.post("/agent/chat", json={"message": "hello"})
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    # Check it starts with "hello" instead of expecting "placeholder"
    assert data["reply"].lower().startswith("hello")



def test_chat_ui():
    res = client.get("/chat")
    assert res.status_code == 200
    assert "Chat with Agent" in res.text
