from fastapi.testclient import TestClient

from src.app import app


def test_rejects_nonlocal_host():
    with TestClient(app, base_url="http://untrusted.example") as client:
        assert client.get("/").status_code == 400


def test_rejects_cross_origin_request():
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/api/chat", json={"question": "test"}, headers={"origin": "https://untrusted.example"})
        assert response.status_code == 403


def test_rejects_empty_question():
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.post("/api/chat", json={"question": "   "}).status_code == 422
