from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    assert client.get("/health").json()["status"] == "ok"

def test_empty_scenes_rejected():
    response = client.post("/v1/jobs", json={"title": "Bad", "aspect_ratio": "16:9", "scenes": []})
    assert response.status_code == 422

def test_missing_job_is_404():
    assert client.get("/v1/jobs/not-real").status_code == 404
