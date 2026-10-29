"""/admin/metrics/usage, /quality y /performance contra Postgres real: la respuesta cumple el esquema
UsageMetrics y OpenAPI lo describe. Se omite si no hay base de datos."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.admin_auth import require_admin
from app.database import SessionLocal
from app.main import app
from app.repositories.admin_metrics import performance_metrics, quality_metrics, usage_metrics
from app.schemas.admin_metrics import PerformanceMetrics, QualityMetrics, UsageMetrics


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        session.close()
        pytest.skip("sin Postgres disponible")
    yield session
    session.close()


@pytest.fixture()
def client():
    app.dependency_overrides[require_admin] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(require_admin, None)


def test_usage_repository_matches_schema(db):
    UsageMetrics.model_validate(usage_metrics(db))


def test_usage_endpoint_returns_declared_fields(db, client):
    res = client.get("/admin/metrics/usage")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == set(UsageMetrics.model_fields)
    for row in body["questions_per_day"]:
        assert len(row["day"]) == 10 and isinstance(row["count"], int)


def test_openapi_describes_usage_response(client):
    schema = client.get("/openapi.json").json()
    ref = schema["paths"]["/admin/metrics/usage"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert ref["$ref"].endswith("/UsageMetrics")


def test_quality_repository_matches_schema(db):
    QualityMetrics.model_validate(quality_metrics(db))


def test_quality_endpoint_returns_declared_fields(db, client):
    res = client.get("/admin/metrics/quality")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == set(QualityMetrics.model_fields)
    assert body["avg_similarity_grounded"] is None or isinstance(body["avg_similarity_grounded"], float)
    assert all(b["range"] in {"0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"} for b in body["similarity_histogram"])


def test_openapi_describes_quality_response(client):
    schema = client.get("/openapi.json").json()
    ref = schema["paths"]["/admin/metrics/quality"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert ref["$ref"].endswith("/QualityMetrics")


def test_performance_repository_matches_schema(db):
    PerformanceMetrics.model_validate(performance_metrics(db))


def test_performance_endpoint_sends_numbers_not_strings(db, client):
    res = client.get("/admin/metrics/performance")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == set(PerformanceMetrics.model_fields)
    for value in (*body["latency"].values(), *body["latency_breakdown"].values()):
        assert value is None or isinstance(value, (int, float))
    for row in body["tokens_per_day"]:
        for key in ("prompt_tokens", "completion_tokens", "aux_prompt_tokens", "total_tokens"):
            assert row[key] is None or isinstance(row[key], int)


def test_openapi_describes_performance_response(client):
    schema = client.get("/openapi.json").json()
    ref = schema["paths"]["/admin/metrics/performance"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert ref["$ref"].endswith("/PerformanceMetrics")
