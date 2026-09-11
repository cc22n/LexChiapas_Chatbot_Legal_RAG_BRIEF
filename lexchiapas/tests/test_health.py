"""Tests de /health y /health/ready.

M3 (auditoria 2026-08-06): /health era superficial (200 incondicional);
/health/ready verifica Postgres. Fase 9.8/A6: /health/ready ademas corre un
canario de embeddings cacheado -- sin el, devolvia 200 aunque el modelo de
embeddings estuviera muerto (410) y todo turno de RAG estuviera fallando.

El canario se mockea en estos tests (health._embeddings_ok / health.embed_text)
para no gastar una llamada real a NVIDIA en la suite rapida."""

from fastapi.testclient import TestClient

from app.api import health
from app.main import app


def test_health_is_always_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_ok_when_db_and_embeddings_ok(monkeypatch):
    monkeypatch.setattr(health, "_embeddings_ok", lambda: True)
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "postgres": "ok", "embeddings": "ok"}


def test_health_ready_503_when_db_unreachable(monkeypatch):
    class _BrokenSession:
        def execute(self, *args, **kwargs):
            raise ConnectionError("simulado: Postgres no disponible")

        def close(self):
            pass

    monkeypatch.setattr(health, "SessionLocal", lambda: _BrokenSession())
    monkeypatch.setattr(health, "_embeddings_ok", lambda: True)

    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not ready"
    assert body["postgres"] == "down"


def test_health_ready_503_when_embeddings_down(monkeypatch):
    # A6: el modo de fallo que motivo este canario -- Postgres sano pero
    # embeddings muertos (410), que antes daba 200 con el RAG 100% roto.
    monkeypatch.setattr(health, "_embeddings_ok", lambda: False)
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not ready"
    assert body["embeddings"] == "down"


def test_embeddings_canary_caches_within_ttl(monkeypatch):
    # No debe pegarle a NVIDIA en cada probe: dentro del TTL, un segundo
    # llamado reusa el veredicto cacheado sin re-invocar embed_text.
    calls = {"n": 0}

    def _fake_embed(text, input_type="query"):
        calls["n"] += 1
        return [0.0]

    monkeypatch.setattr(health, "embed_text", _fake_embed)
    monkeypatch.setattr(health, "_embed_canary", None, raising=False)

    assert health._embeddings_ok() is True
    assert health._embeddings_ok() is True
    assert calls["n"] == 1  # segundo llamado servido desde cache
