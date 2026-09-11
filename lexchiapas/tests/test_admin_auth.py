import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import admin_auth
from app.api.admin_auth import (
    SESSION_COOKIE_NAME,
    create_session_cookie,
    require_admin,
)
from app.api.rate_limit import MAX_REQUESTS_PER_WINDOW


class _FakeRequest:
    def __init__(self, cookies: dict[str, str] | None = None, client_host: str = "127.0.0.1"):
        self.cookies = cookies or {}
        self.client = SimpleNamespace(host=client_host) if client_host else None


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    # get_settings() esta cacheado con @lru_cache y lee del .env real -- para
    # que los tests sean deterministas sin importar la maquina/entorno, se
    # sustituye por un objeto controlado en vez de depender del .env real.
    fake_settings = SimpleNamespace(admin_api_key="test-admin-key-123", secret_key="")
    monkeypatch.setattr(admin_auth, "get_settings", lambda: fake_settings)
    return fake_settings


def test_session_cookie_round_trips():
    token = create_session_cookie()
    assert admin_auth._session_cookie_is_valid(token)


def test_session_cookie_rejects_tampered_signature():
    token = create_session_cookie()
    timestamp, _signature = token.split(".", 1)
    tampered = f"{timestamp}.0000000000000000000000000000000000000000000000000000000000000000"
    assert not admin_auth._session_cookie_is_valid(tampered)


def test_session_cookie_rejects_malformed_token():
    assert not admin_auth._session_cookie_is_valid("no-tiene-punto")
    assert not admin_auth._session_cookie_is_valid("")


def test_session_cookie_rejects_expired_token(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr(time, "time", lambda: fake_now[0])
    token = create_session_cookie()

    fake_now[0] += admin_auth.SESSION_MAX_AGE_SECONDS + 1
    assert not admin_auth._session_cookie_is_valid(token)


def test_session_cookie_rejects_future_timestamp():
    # timestamp en el futuro (reloj desincronizado o token fabricado) -- la
    # validacion exige 0 <= age_seconds, nunca negativo.
    signature = admin_auth.hmac.new(
        admin_auth._signing_key().encode(), b"99999999999", admin_auth.hashlib.sha256
    ).hexdigest()
    assert not admin_auth._session_cookie_is_valid(f"99999999999.{signature}")


def test_require_admin_accepts_correct_header():
    require_admin(_FakeRequest(), x_admin_api_key="test-admin-key-123")  # no debe lanzar


def test_require_admin_rejects_wrong_header():
    with pytest.raises(HTTPException) as exc_info:
        require_admin(_FakeRequest(), x_admin_api_key="wrong-key")
    assert exc_info.value.status_code == 401


def test_require_admin_rejects_wrong_length_header_without_crashing():
    # hmac.compare_digest exige que ambos lados tengan el mismo tipo, pero
    # tolera longitudes distintas sin lanzar -- solo debe dar 401, nunca un
    # error 500 por un header mas corto/largo que la key real.
    with pytest.raises(HTTPException) as exc_info:
        require_admin(_FakeRequest(), x_admin_api_key="x")
    assert exc_info.value.status_code == 401


def test_require_admin_accepts_valid_session_cookie():
    token = create_session_cookie()
    require_admin(_FakeRequest(cookies={SESSION_COOKIE_NAME: token}), x_admin_api_key=None)


def test_require_admin_rejects_missing_credentials():
    with pytest.raises(HTTPException) as exc_info:
        require_admin(_FakeRequest(), x_admin_api_key=None)
    assert exc_info.value.status_code == 401


def test_require_admin_rejects_invalid_cookie():
    with pytest.raises(HTTPException):
        require_admin(_FakeRequest(cookies={SESSION_COOKIE_NAME: "garbage"}), x_admin_api_key=None)


def test_require_admin_rate_limits_header_brute_force():
    # BUG REAL (2026-08-04, auditoria de seguridad): antes de este fix,
    # require_admin no llamaba a enforce_rate_limit, asi que cualquier
    # endpoint admin protegido con el header X-Admin-Api-Key aceptaba
    # intentos ilimitados de adivinar la key -- incluido el propio dashboard
    # de Next.js, que valida la key pegandole a /admin/metrics/usage en vez
    # de /admin/login. IP dedicada para no compartir bucket con los demas
    # tests de este archivo (que usan el default "127.0.0.1").
    ip = "203.0.113.42"
    for _ in range(MAX_REQUESTS_PER_WINDOW):
        with pytest.raises(HTTPException) as exc_info:
            require_admin(_FakeRequest(client_host=ip), x_admin_api_key="wrong-key")
        assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info:
        require_admin(_FakeRequest(client_host=ip), x_admin_api_key="wrong-key")
    assert exc_info.value.status_code == 429


def test_require_admin_rate_limit_does_not_block_cookie_path():
    # El bucket de rate limit solo se toca cuando llega el header -- la
    # cookie de sesion (uso normal del dashboard, polling de metricas) no
    # debe verse afectada aunque el mismo IP haya agotado el limite via
    # header en otra request.
    ip = "203.0.113.99"
    for _ in range(MAX_REQUESTS_PER_WINDOW + 1):
        with pytest.raises(HTTPException):
            require_admin(_FakeRequest(client_host=ip), x_admin_api_key="wrong-key")

    token = create_session_cookie()
    require_admin(_FakeRequest(cookies={SESSION_COOKIE_NAME: token}, client_host=ip), x_admin_api_key=None)


# --- Revocacion de logout (Fase 9.8, pentest MEDIA) ---


class _FakeRedis:
    """Redis en memoria minimo para probar la blocklist sin depender del
    redis-server real (que puede o no estar corriendo en el entorno de test)."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def set(self, key, value, ex=None, nx=False):
        self.store[key] = value
        return True

    def exists(self, key):
        return 1 if key in self.store else 0


def test_revoked_session_cookie_is_rejected(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(admin_auth, "_get_redis_client", lambda: fake)

    token = create_session_cookie()
    assert admin_auth._session_cookie_is_valid(token)  # valida antes de revocar

    admin_auth.revoke_session(token)
    assert not admin_auth._session_cookie_is_valid(token)  # ya no, tras logout


def test_revocation_fails_open_when_redis_unavailable(monkeypatch):
    def _boom():
        raise ConnectionError("simulado: Redis no disponible")

    monkeypatch.setattr(admin_auth, "_get_redis_client", _boom)

    token = create_session_cookie()
    # revoke_session no debe lanzar aunque Redis este caido...
    admin_auth.revoke_session(token)
    # ...y la validacion hace fail-open: un Redis caido no bloquea a un admin
    # legitimo (la cookie igual expira sola por edad).
    assert admin_auth._session_cookie_is_valid(token)
