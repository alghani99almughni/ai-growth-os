from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_the_deployed_commit(monkeypatch):
    # The post-deploy QA workflow waits until /health shows the pushed commit; /health used to omit it.
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123def456")
    assert client.get("/health").json()["commit"] == "abc123def456"
    monkeypatch.delenv("RENDER_GIT_COMMIT")
    assert client.get("/health").json()["commit"] == "unknown"
