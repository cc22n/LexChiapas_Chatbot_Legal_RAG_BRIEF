"""/admin/metrics/usage contra Postgres real: la respuesta cumple el esquema
UsageMetrics y OpenAPI lo describe. Se omite si no hay base de datos."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.admin_auth import require_admin
from app.database import SessionLocal
from app.main import app
from app.repositories.admin_metrics import usage_metrics
from app.schemas.admin_metrics import UsageMetrics


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
