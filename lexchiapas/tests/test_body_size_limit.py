"""Test de regresion para el hallazgo M5 de la auditoria de salud del
backend (2026-08-06): sin limite de tamano de payload, un POST con un body
JSON gigante forzaba a Starlette a leerlo completo en memoria antes de que
Pydantic pudiera rechazarlo por max_length."""

from fastapi.testclient import TestClient

from app.main import MAX_BODY_SIZE_BYTES, app


def test_rejects_oversized_payload_with_413():
    oversized_body = b"x" * (MAX_BODY_SIZE_BYTES + 1)
    with TestClient(app) as client:
        response = client.post(
            "/health",  # cualquier ruta -- el middleware corre ANTES del routing
            content=oversized_body,
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 413


def test_allows_normal_sized_payload():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
