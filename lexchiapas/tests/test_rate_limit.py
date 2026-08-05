import time

import pytest
from fastapi import HTTPException

from app.api import rate_limit
from app.api.rate_limit import MAX_REQUESTS_PER_WINDOW, enforce_rate_limit


@pytest.fixture(autouse=True)
def _clean_rate_limit_state():
    # Cada test arranca con el dict global vacio -- sin esto, el orden real
    # de ejecucion de tests contaminaria los buckets entre casos (el estado
    # es un dict a nivel de modulo, sobrevive entre tests si no se limpia).
    rate_limit._requests_by_session.clear()
    rate_limit._calls_since_sweep = 0
    yield
    rate_limit._requests_by_session.clear()
    rate_limit._calls_since_sweep = 0


def test_allows_requests_under_the_limit():
    for _ in range(MAX_REQUESTS_PER_WINDOW):
        enforce_rate_limit("session-a")  # no debe lanzar


def test_blocks_requests_over_the_limit():
    for _ in range(MAX_REQUESTS_PER_WINDOW):
        enforce_rate_limit("session-b")

    with pytest.raises(HTTPException) as exc_info:
        enforce_rate_limit("session-b")
    assert exc_info.value.status_code == 429


def test_different_keys_have_independent_buckets():
    # BUG REAL corregido 2026-08-04: session_id (client-supplied) y la IP
    # real se tratan como buckets INDEPENDIENTES en chat_web.py -- agotar
    # uno no debe agotar el otro, y dos claves cualquiera no deben
    # interferir entre si.
    for _ in range(MAX_REQUESTS_PER_WINDOW):
        enforce_rate_limit("session-c")

    enforce_rate_limit("ip:1.2.3.4")  # bucket distinto, no debe lanzar


def test_sliding_window_expires_old_requests(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    for _ in range(MAX_REQUESTS_PER_WINDOW):
        enforce_rate_limit("session-d")

    with pytest.raises(HTTPException):
        enforce_rate_limit("session-d")

    # Avanza el reloj mas alla de la ventana -- los timestamps viejos deben
    # expirar y liberar cupo de nuevo.
    fake_now[0] += rate_limit.WINDOW_SECONDS + 1
    enforce_rate_limit("session-d")  # no debe lanzar


def test_sweep_removes_stale_keys_but_keeps_active_ones(monkeypatch):
    # BUG REAL corregido 2026-08-04 (hallazgo #7): un defaultdict nunca
    # borraba una clave sola -- cada session_id/IP distinto que se vio
    # alguna vez se quedaba en el dict para siempre, incluso ya expirado.
    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    enforce_rate_limit("stale-session")  # se usa una vez y nunca vuelve

    fake_now[0] += rate_limit.WINDOW_SECONDS + 1
    monkeypatch.setattr(rate_limit, "SWEEP_EVERY_N_CALLS", 1)

    enforce_rate_limit("active-session")  # dispara el sweep (cada 1 llamada)

    assert "stale-session" not in rate_limit._requests_by_session
    assert "active-session" in rate_limit._requests_by_session
