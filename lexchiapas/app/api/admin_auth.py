import hashlib
import hmac
import logging
import time

import redis
from fastapi import Header, HTTPException, Request

from app.api.rate_limit import enforce_rate_limit
from app.config import get_settings

logger = logging.getLogger("lexchiapas.admin_auth")

SESSION_COOKIE_NAME = "lexchiapas_admin_session"
SESSION_MAX_AGE_SECONDS = 24 * 3600

_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    # Mismo patron/racional que app.rag.memory / app.workers.alerting_tasks
    # (RESP2 + timeouts explicitos por el redis-server 5.0.14 local).
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            protocol=2,
            socket_timeout=3,
            socket_connect_timeout=3,
        )
    return _redis_client


def _revocation_key(token: str) -> str:
    # sha256 del valor completo de la cookie: revoca esa cookie puntual sin
    # tener que agregar un jti al formato firmado (Fase 9.8, pentest MEDIA).
    return "admin:revoked:" + hashlib.sha256(token.encode()).hexdigest()


def revoke_session(token: str) -> None:
    """Marca una cookie de sesion como revocada en Redis, con TTL = vida
    restante de la cookie (pasado ese punto ya expira por edad de todas
    formas). Fail-open: si Redis no responde, se loguea y no se lanza -- la
    cookie igual caduca sola en <=24h."""
    try:
        timestamp_str, _ = token.split(".", 1)
        remaining = SESSION_MAX_AGE_SECONDS - (time.time() - int(timestamp_str))
    except (ValueError, TypeError):
        remaining = SESSION_MAX_AGE_SECONDS
    ttl = max(1, int(remaining))
    try:
        _get_redis_client().set(_revocation_key(token), "1", ex=ttl)
    except Exception as exc:  # noqa: BLE001 - revocacion best-effort, ver docstring
        logger.warning("admin_auth: no se pudo revocar la sesion en Redis: %s", exc)


def _session_is_revoked(token: str) -> bool:
    """True si la cookie esta en la blocklist. Fail-open ante Redis caido
    (coherente con la postura best-effort de Redis en el repo): un Redis caido
    no debe bloquear a un admin legitimo; la cookie igual expira por edad."""
    try:
        return _get_redis_client().exists(_revocation_key(token)) > 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin_auth: no se pudo consultar la blocklist en Redis: %s", exc)
        return False


def _signing_key() -> str:
    settings = get_settings()
    # Fase 1: sin SECRET_KEY propia, reusa admin_api_key para firmar. Ver nota
    # en app/config.py.
    return settings.secret_key or settings.admin_api_key


def create_session_cookie() -> str:
    timestamp = str(int(time.time()))
    signature = hmac.new(_signing_key().encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    return f"{timestamp}.{signature}"


def _session_cookie_is_valid(token: str) -> bool:
    try:
        timestamp_str, signature = token.split(".", 1)
    except ValueError:
        return False

    expected_signature = hmac.new(
        _signing_key().encode(), timestamp_str.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return False

    age_seconds = time.time() - int(timestamp_str)
    if not (0 <= age_seconds <= SESSION_MAX_AGE_SECONDS):
        return False

    # Fase 9.8 (pentest MEDIA): incluso una cookie con firma y edad validas
    # queda rechazada si se hizo logout con ella -- sin esto, "cerrar sesion"
    # solo borraba la cookie del navegador pero el valor copiado seguia valido
    # hasta 24h.
    return not _session_is_revoked(token)


def require_admin(
    request: Request,
    x_admin_api_key: str | None = Header(default=None),
) -> None:
    """Acepta CUALQUIERA de los dos: el header X-Admin-Api-Key (uso original,
    scripts/herramientas) o la cookie de sesion de POST /admin/login (uso
    nuevo, dashboard de Next.js). No se retira el header para no romper nada
    que ya lo use.
    """
    settings = get_settings()
    if x_admin_api_key is not None:
        # BUG REAL (hallazgo de auditoria de seguridad, 2026-08-04): antes de
        # este fix, cualquier endpoint con Depends(require_admin) aceptaba el
        # header X-Admin-Api-Key sin rate limit, mientras que solo POST
        # /admin/login lo tenia. El propio dashboard de Next.js
        # (adminApi.ts:verifyAdminApiKey) valida la key pegandole al header
        # contra /admin/metrics/usage en vez de /admin/login, lo que dejaba
        # fuerza bruta ilimitada contra la credencial maestra. Se reusa el
        # mismo bucket "admin_login:<ip>" que /admin/login para que ambos
        # caminos de intento compartan un solo contador por IP.
        client_host = request.client.host if request.client else "unknown"
        enforce_rate_limit(f"admin_login:{client_host}")
        if settings.admin_api_key and hmac.compare_digest(
            x_admin_api_key, settings.admin_api_key
        ):
            return

    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if session_cookie and _session_cookie_is_valid(session_cookie):
        return

    raise HTTPException(status_code=401, detail="invalid admin api key or session")
