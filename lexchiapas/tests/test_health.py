"""Test de regresion para el hallazgo M3 de la auditoria de salud del
backend (2026-08-06): /health era superficial (200 incondicional, sin
verificar Postgres). /health/ready si lo verifica."""

from fastapi.testclient import TestClient

from app.api import health
from app.main import app


def test_health_is_always_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_returns_ok_when_db_is_reachable():
    # DB real de este entorno -- mismo criterio que otros tests de este
    # proyecto que ya tocan Postgres real (test_ingestion_atomicity.py).
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_returns_503_when_db_is_unreachable(monkeypatch):
    class _BrokenSession:
        def execute(self, *args, **kwargs):
            raise ConnectionError("simulado: Postgres no disponible")

        def close(self):
            pass

    monkeypatch.setattr(health, "SessionLocal", lambda: _BrokenSession())

    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}
