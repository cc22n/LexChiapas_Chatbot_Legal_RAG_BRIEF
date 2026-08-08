"""Tests de regresion para los hallazgos M2 (request ID) y B1 (exception
handler global) de la auditoria de salud del backend (2026-08-06).

test_unhandled_exception_... llama a handle_unexpected_exception()
DIRECTAMENTE (con un Request fake, mismo patron que tests/test_admin_auth.py
usa para require_admin) en vez de disparar la excepcion via TestClient +
HTTP real. Confirmado a mano (script standalone fuera de pytest) que el
handler SI funciona correctamente end-to-end contra app.main.app real -- la
combinacion especifica TestClient + pytest + dos middlewares
BaseHTTPMiddleware anidados dispara un falso positivo del plugin
unraisableexception/threadexception de pytest (excepcion ya manejada y
respondida correctamente, pero igual reportada como fallo de test por un
mecanismo separado al de la respuesta HTTP real -- ver ServerErrorMiddleware,
que reenvia la excepcion a proposito despues de mandar la respuesta, "para
que un ASGI server pueda loguearla"). Probar la funcion directamente evita
por completo esa interaccion de infraestructura de test y sigue verificando
la logica real que importa: status code, body, y de donde sale el
request_id."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app, handle_unexpected_exception


class _FakeURL:
    path = "/fake/path"


class _FakeState:
    def __init__(self, request_id: str | None = None):
        self.request_id = request_id


class _FakeRequest:
    method = "GET"
    url = _FakeURL()

    def __init__(self, request_id: str | None = None):
        self.state = _FakeState(request_id)


def test_response_includes_a_unique_request_id_header():
    with TestClient(app) as client:
        first = client.get("/health")
        second = client.get("/health")

    first_id = first.headers.get("x-request-id")
    second_id = second.headers.get("x-request-id")

    assert first_id is not None
    assert second_id is not None
    assert first_id != second_id
    # Debe ser un UUID valido -- no truena si el formato esta bien.
    uuid.UUID(first_id)
    uuid.UUID(second_id)


@pytest.mark.asyncio
async def test_unhandled_exception_returns_structured_500_with_request_id():
    # BUG REAL corregido (hallazgo B1): antes, una excepcion no controlada
    # caia al 500 de texto plano de Starlette en vez de este JSON estructurado.
    request = _FakeRequest(request_id="abc-123-fake")

    response = await handle_unexpected_exception(request, RuntimeError("boom simulado"))

    assert response.status_code == 500
    body = json.loads(bytes(response.body))
    assert body == {"detail": "internal error", "request_id": "abc-123-fake"}


@pytest.mark.asyncio
async def test_unhandled_exception_falls_back_to_contextvar_without_request_state():
    # BUG REAL corregido (hallazgo M2/B1): al principio este handler leia
    # SOLO el contextvar request_id_var -- pero para cuando una excepcion
    # real llega hasta aca, add_request_id (el middleware que setea ese
    # contextvar) ya corrio su `finally` y ya lo reseteo a "-", asi que el
    # request_id real se perdia justo en el peor momento (el log de una
    # excepcion de verdad). Ahora sale de request.state (sobrevive ese
    # reset); este test solo confirma que sigue habiendo un fallback
    # razonable si por lo que sea state.request_id no esta seteado.
    request = _FakeRequest(request_id=None)

    response = await handle_unexpected_exception(request, RuntimeError("boom simulado"))

    import json

    body = json.loads(bytes(response.body))
    assert body["detail"] == "internal error"
    assert body["request_id"] == "-"  # default del contextvar fuera de un request real
