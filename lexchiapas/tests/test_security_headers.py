"""Security headers del backend (Fase 9.8/A4).

Regresion: hasta la auditoria 2026-09-09 el backend no emitia NINGUN header
de seguridad. Se agrego un middleware (app.main.security_headers). Estos tests
fijan que los headers de bajo riesgo esten presentes en respuestas normales y
que la CSP estricta se exceptue en /openapi.json (Swagger/docs, que sirve
HTML+scripts y romperia con default-src 'none')."""

from fastapi.testclient import TestClient

from app.main import app

_ALWAYS_ON = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


def test_security_headers_present_on_normal_response():
    with TestClient(app) as client:
        resp = client.get("/health")
    for header, value in _ALWAYS_ON.items():
        assert resp.headers.get(header) == value
    assert "content-security-policy" in resp.headers
    assert "default-src 'none'" in resp.headers["content-security-policy"]


def test_csp_exempted_on_openapi_docs_path():
    # /openapi.json sirve el schema que Swagger UI consume; una CSP
    # default-src 'none' romperia /docs, por eso se exceptua.
    with TestClient(app) as client:
        resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "content-security-policy" not in resp.headers
    # los headers de bajo riesgo si siguen presentes incluso en docs
    assert resp.headers.get("x-content-type-options") == "nosniff"
