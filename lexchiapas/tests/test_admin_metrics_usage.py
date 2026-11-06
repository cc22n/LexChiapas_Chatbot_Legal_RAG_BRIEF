"""/admin/metrics/usage, /quality, /performance, /guardrails, /agent y /golden_dataset contra Postgres real: la respuesta cumple el esquema
UsageMetrics y OpenAPI lo describe. Se omite si no hay base de datos."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.admin_auth import require_admin
from app.database import SessionLocal
from app.main import app
from app.repositories.admin_metrics import agent_metrics, golden_dataset_metrics, guardrails_metrics, performance_metrics, quality_metrics, usage_metrics
from app.schemas.admin_metrics import AgentMetrics, GoldenDatasetMetrics, GuardrailsMetrics, PerformanceMetrics, QualityMetrics, UsageMetrics


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


def test_guardrails_repository_matches_schema(db):
    GuardrailsMetrics.model_validate(guardrails_metrics(db))


def test_guardrails_endpoint_and_openapi(db, client):
    res = client.get("/admin/metrics/guardrails")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == set(GuardrailsMetrics.model_fields)
    assert isinstance(body["total_out_of_scope"], int) and isinstance(body["jailbreak_attempts"], int)
    schema = client.get("/openapi.json").json()
    ref = schema["paths"]["/admin/metrics/guardrails"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert ref["$ref"].endswith("/GuardrailsMetrics")


def test_agent_repository_matches_schema(db):
    AgentMetrics.model_validate(agent_metrics(db))


def test_agent_endpoint_and_openapi(db, client):
    res = client.get("/admin/metrics/agent")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == set(AgentMetrics.model_fields)
    assert body["avg_intentos"] is None or isinstance(body["avg_intentos"], float)
    schema = client.get("/openapi.json").json()
    ref = schema["paths"]["/admin/metrics/agent"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert ref["$ref"].endswith("/AgentMetrics")


def test_golden_repository_matches_schema(db):
    GoldenDatasetMetrics.model_validate(golden_dataset_metrics(db))


def test_golden_endpoint_and_openapi(db, client):
    res = client.get("/admin/metrics/golden_dataset")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"latest", "history"}
    if body["latest"] is not None:
        assert isinstance(body["latest"]["cases"], list)
    schema = client.get("/openapi.json").json()
    ref = schema["paths"]["/admin/metrics/golden_dataset"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert ref["$ref"].endswith("/GoldenDatasetMetrics")


def test_golden_schema_accepts_partial_run_with_null_columns():
    GoldenDatasetMetrics.model_validate(
        {"latest": {"id": 1, "started_at": None, "completed_at": None, "total": None, "passed": None,
                    "xfailed_known": None, "failed": None, "duration_ms": None, "cases": []},
         "history": []}
    )
