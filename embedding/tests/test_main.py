"""Tests for the embedding microservice."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from main import app
    with TestClient(app) as tc:
        yield tc


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_embeddings_single_string(client):
    response = client.post("/v1/embeddings", json={"input": "hello"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert len(data[0]["embedding"]) == 384


def test_embeddings_list_input(client):
    response = client.post("/v1/embeddings", json={"input": ["hello", "world"]})
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


def test_embeddings_empty_input_returns_400(client):
    response = client.post("/v1/embeddings", json={"input": [], "model": "bge-small-en-v1.5"})
    assert response.status_code == 400


def test_embeddings_model_failure_returns_500(client, monkeypatch):
    """When model.embed() raises, the endpoint returns 500."""
    from unittest.mock import MagicMock
    import main

    # Replace model with one that crashes on embed
    crash = MagicMock()
    crash.embed.side_effect = RuntimeError("model crash")
    monkeypatch.setattr(main, "model", crash)

    response = client.post("/v1/embeddings", json={"input": "hello"})
    assert response.status_code == 500
