"""Alerta operativa minima viable (Fase 9.8/C3).

Contexto: el incidente del 2026-08-25 (modelo de embeddings muerto, 410) no se
detecto en ~2 dias porque no habia NINGUNA alerta activa -- solo logs pasivos
que nadie miraba. Esta tarea de Celery Beat corre cada 5 min y avisa por
Telegram si (a) el modelo de embeddings dejo de responder, o (b) hay un pico
de turnos con error de sistema. Es deliberadamente simple y sin dependencias
externas de pago (Sentry, PagerDuty): usa el mismo bot de Telegram y el mismo
Redis que ya tiene el proyecto. Nunca lanza -- una falla del alerting jamas
debe tumbar al worker.

Auditoria 2026-10-24: el canario de embeddings NO cubria los modelos LLM. Los
tres modelos de NVIDIA de llm.fallback_order llevaban semanas devolviendo HTTP
410 (fin de vida) y todo el trafico caia en silencio al ultimo recurso, que
tiene credito limitado. llm_models_canary (cada 6 h) prueba cada entrada de
fallback_order y avisa solo de fallos PERMANENTES (modelo retirado, credenciales
rechazadas, credito agotado), nunca de timeouts/429 transitorios.
"""

import logging

import httpx
import redis

from app.config import get_ai_config, get_settings
from app.database import SessionLocal
from app.llm.providers import embed_text, get_client_for_provider
from app.workers.celery_app import celery_app

logger = logging.getLogger("lexchiapas.alerting")

# Ventana y umbral para el pico de errores de sistema (found_answer IS NULL +
# error_message, ver app.bots.conversation_store y app.models.Message).
_SYSTEM_ERROR_WINDOW_MINUTES = 10
_SYSTEM_ERROR_THRESHOLD = 3
# Cooldown por tipo de alerta para no spamear cada 5 min durante un incidente.
_ALERT_COOLDOWN_SECONDS = 30 * 60

_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    # Mismo patron/racional que app.rag.memory._get_redis_client (RESP2 +
    # timeouts explicitos por el redis-server 5.0.14 local).
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


def _cooldown_allows(kind: str) -> bool:
    """True si se debe enviar la alerta ahora (no hay cooldown activo para
    este tipo). Fail-open: si Redis no responde, se permite enviar -- mejor un
    alerta de mas que un silencio durante un incidente."""
    try:
        # SET key value NX EX=cooldown -> devuelve True solo si NO existia.
        was_set = _get_redis_client().set(f"alert:cooldown:{kind}", "1", nx=True, ex=_ALERT_COOLDOWN_SECONDS)
        return bool(was_set)
    except Exception as exc:  # noqa: BLE001 - el alerting nunca debe tumbar el worker
        logger.warning("alerting: cooldown check fallo (%s), se permite enviar por defecto", exc)
        return True


def send_admin_telegram_alert(text: str) -> bool:
    """Envia un mensaje al chat admin via la HTTP API de Telegram (sync, sin
    el Bot async de python-telegram-bot que necesitaria un event loop dentro
    del worker). Devuelve True si se envio. No lanza."""
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.admin_telegram_chat_id
    if not token or not chat_id:
        logger.warning("alerting: telegram_bot_token/admin_telegram_chat_id sin configurar, no se envia alerta")
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("alerting: telegram respondio %s: %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # noqa: BLE001 - el alerting nunca debe tumbar el worker
        logger.warning("alerting: fallo al enviar a telegram: %s", exc)
        return False


def _check_embeddings() -> str | None:
    """Canario de embeddings: una llamada real a embed_text. Devuelve un texto
    de alerta si esta caido, o None si esta sano."""
    try:
        embed_text("ping")
        return None
    except Exception as exc:  # noqa: BLE001 - cualquier fallo aca es alerta-worthy
        logger.error("alerting: canario de embeddings FALLO: %s: %s", type(exc).__name__, exc)
        return (
            "[LexChiapas] EMBEDDINGS CAIDOS: el modelo de embeddings no responde "
            f"({type(exc).__name__}). TODO turno de RAG esta fallando. Revisa "
            "embeddings.model en ai_config.json (posible fin de vida/410) y usa "
            "POST /admin/config/reload tras corregirlo."
        )


def _check_system_error_surge() -> str | None:
    from sqlalchemy import text

    db = SessionLocal()
    try:
        count = db.execute(
            text(
                """
                SELECT count(*) FROM messages
                WHERE role = 'assistant'
                  AND found_answer IS NULL
                  AND error_message IS NOT NULL
                  AND created_at > now() - make_interval(mins => :mins)
                """
            ),
            {"mins": _SYSTEM_ERROR_WINDOW_MINUTES},
        ).scalar_one()
    except Exception as exc:  # noqa: BLE001
        logger.warning("alerting: no se pudo contar errores de sistema: %s", exc)
        return None
    finally:
        db.close()

    if count >= _SYSTEM_ERROR_THRESHOLD:
        logger.error("alerting: pico de errores de sistema: %d en %d min", count, _SYSTEM_ERROR_WINDOW_MINUTES)
        return (
            f"[LexChiapas] {count} turnos con ERROR DE SISTEMA en los ultimos "
            f"{_SYSTEM_ERROR_WINDOW_MINUTES} min (found_answer IS NULL). Revisa "
            "los logs (proveedores LLM caidos, DB, o un bug del pipeline)."
        )
    return None


@celery_app.task(name="app.workers.alerting_tasks.health_canary")
def health_canary() -> dict:
    """Corre cada 5 min (ver beat_schedule en celery_app). Revisa embeddings y
    pico de errores; envia a Telegram con cooldown por tipo. Devuelve un
    resumen para que quede en el log del worker."""
    result: dict[str, object] = {"embeddings_down": False, "system_error_surge": False, "sent": []}

    for kind, message in (("embeddings", _check_embeddings()), ("system_errors", _check_system_error_surge())):
        if message is None:
            continue
        result[f"{'embeddings_down' if kind == 'embeddings' else 'system_error_surge'}"] = True
        if _cooldown_allows(kind) and send_admin_telegram_alert(message):
            result["sent"].append(kind)  # type: ignore[attr-defined]

    return result


# Estados que significan que una entrada de fallback_order ya no sirve de forma
# PERMANENTE. Todo lo demas (timeout, 5xx, 429 por ritmo) es transitorio y no
# alerta: con proveedores intermitentes seria ruido.
_LLM_GONE_STATUSES = (404, 410)
_LLM_AUTH_STATUSES = (401, 403)
_LLM_PROBLEM_LABELS = {
    "gone": "modelo retirado (fin de vida)",
    "auth": "credenciales rechazadas",
    "quota": "credito agotado",
}


def _classify_llm_error(exc: Exception) -> str:
    """'gone' | 'auth' | 'quota' | 'transient'."""
    status = getattr(exc, "status_code", None)
    if status in _LLM_GONE_STATUSES:
        return "gone"
    if status in _LLM_AUTH_STATUSES:
        return "auth"
    body = str(getattr(exc, "body", "") or exc).lower()
    # OpenAI: 429 con code insufficient_quota; Moonshot: exceeded_current_quota_error.
    if status == 402 or (status == 429 and ("insufficient_quota" in body or "exceeded_current_quota" in body)):
        return "quota"
    return "transient"


def _check_llm_models() -> tuple[str | None, dict]:
    """Prueba cada entrada de llm.fallback_order con una llamada minima real
    (max_tokens=16; usa la temperatura propia de la entrada si la tiene, p. ej.
    Kimi exige 1). Devuelve (mensaje_de_alerta | None, resumen)."""
    llm_config = get_ai_config()["llm"]
    working: list[str] = []
    transient: list[str] = []
    problems: list[tuple[str, str]] = []

    for entry in llm_config["fallback_order"]:
        label = f"{entry['provider']}/{entry['model']}"
        try:
            client = get_client_for_provider(entry["provider"], timeout=20.0)
            client.chat.completions.create(
                model=entry["model"],
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=16,
                temperature=entry.get("temperature", llm_config.get("temperature", 0.1)),
            )
            working.append(label)
        except Exception as exc:  # noqa: BLE001 - el alerting nunca debe tumbar el worker
            kind = _classify_llm_error(exc)
            if kind == "transient":
                transient.append(label)
                logger.warning("alerting: %s fallo de forma transitoria: %s", label, type(exc).__name__)
            else:
                problems.append((label, kind))
                logger.error("alerting: %s NO disponible (%s): %s", label, kind, type(exc).__name__)

    summary = {"working": working, "transient": transient, "problems": problems}
    if not problems:
        return None, summary

    lines = [f"- {label}: {_LLM_PROBLEM_LABELS[kind]}" for label, kind in problems]
    message = "[LexChiapas] MODELOS LLM NO DISPONIBLES en llm.fallback_order:\n" + "\n".join(lines)
    if working:
        message += "\nSiguen respondiendo: " + ", ".join(working) + "."
    else:
        message += "\nNINGUNA entrada respondio bien: el bot puede no generar respuestas."
    message += (
        "\nRevisa llm.fallback_order en ai_config.json (listar /v1/models y probar con una llamada real "
        "antes de agregar un modelo) y usa POST /admin/config/reload tras corregirlo."
    )
    return message, summary


@celery_app.task(name="app.workers.alerting_tasks.llm_models_canary")
def llm_models_canary() -> dict:
    """Corre cada 6 h (ver beat_schedule). Avisa por Telegram de modelos LLM
    retirados, credenciales rechazadas o credito agotado, con cooldown. Nunca
    lanza."""
    result: dict[str, object] = {"problems": [], "sent": False}
    try:
        message, summary = _check_llm_models()
    except Exception as exc:  # noqa: BLE001
        logger.warning("alerting: llm_models_canary fallo: %s", exc)
        return result
    result["problems"] = summary["problems"]
    result["working"] = summary["working"]
    if message and _cooldown_allows("llm_models") and send_admin_telegram_alert(message):
        result["sent"] = True
    return result
