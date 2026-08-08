import logging

import redis

from app.config import get_settings

logger = logging.getLogger("lexchiapas.telegram_dedup")

# Cubre con margen amplio la ventana real en la que Telegram podria
# reintentar la entrega de un mismo update (timeouts de red, o el propio
# webhook tardando en responder -- ver app.api.telegram_webhook).
UPDATE_SEEN_TTL_SECONDS = 24 * 60 * 60

_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        # Mismo criterio que app.rag.memory._get_redis_client: protocol=2
        # (RESP2) porque el redis-server local de este proyecto es 5.0.14,
        # que no soporta RESP3. socket_timeout/socket_connect_timeout
        # explicitos (auditoria de salud del backend, 2026-08-06, hallazgo
        # M6): sin esto, una conexion colgada (no rechazada) a un Redis
        # remoto podria colgar el webhook completo en vez de fallar rapido
        # y caer al camino "se procesa sin deduplicar" de abajo.
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            protocol=2,
            socket_timeout=3,
            socket_connect_timeout=3,
        )
    return _redis_client


def _update_seen_key(update_id: int) -> str:
    return f"telegram:update_seen:{update_id}"


def already_processed(update_id: int) -> bool:
    """True si este update_id de Telegram YA se vio antes (duplicado real,
    ej. reintento de entrega de Telegram); False si es la primera vez --y en
    ese caso lo marca como visto para la proxima llamada, en la misma
    operacion atomica (SET ... NX).

    BUG REAL corregido (auditoria de salud del backend, 2026-08-06, hallazgo
    A1): antes no habia deduplicacion -- un reintento de Telegram (mas
    probable ahora que el pipeline puede tardar mas de lo que Telegram
    espera, ver hallazgo A2 en app.api.telegram_webhook) reprocesaba el
    turno completo: llamada LLM duplicada (costo real), fila Message
    duplicada, el usuario recibia la respuesta dos veces.

    Best-effort: si Redis falla por cualquier motivo, se asume que NO se
    vio antes (False, se procesa igual) -- un reproceso ocasional bajo Redis
    caido es preferible a que un Redis caido bloquee TODOS los mensajes de
    Telegram (misma filosofia que app.rag.memory: la correccion del sistema
    nunca depende de que Redis este arriba).
    """
    key = _update_seen_key(update_id)
    try:
        # SET key value NX EX ttl: solo escribe si la key NO existia ya --
        # devuelve True si el SET tuvo efecto (primera vez que se ve este
        # update_id), None si la key ya existia (duplicado).
        newly_set = _get_redis_client().set(key, "1", nx=True, ex=UPDATE_SEEN_TTL_SECONDS)
        return not newly_set
    except Exception as exc:
        logger.warning(
            "telegram dedup: Redis no disponible, se procesa sin deduplicar (update_id=%s): %s",
            update_id, exc,
        )
        return False
