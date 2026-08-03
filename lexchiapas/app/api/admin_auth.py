import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Request

from app.config import get_settings

SESSION_COOKIE_NAME = "lexchiapas_admin_session"
SESSION_MAX_AGE_SECONDS = 24 * 3600


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
    return 0 <= age_seconds <= SESSION_MAX_AGE_SECONDS


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
    if settings.admin_api_key and x_admin_api_key == settings.admin_api_key:
        return

    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if session_cookie and _session_cookie_is_valid(session_cookie):
        return

    raise HTTPException(status_code=401, detail="invalid admin api key or session")
