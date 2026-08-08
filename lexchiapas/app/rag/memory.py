import json

import redis
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Message

# Fase 2.6 (LexChiapas_Memoria_Conversacional.md): memoria de corto plazo por
# ventana deslizante. NO memoria semantica con embeddings (explicitamente
# opcional/futuro segun el documento fuente) -- solo los ultimos N mensajes
# de la conversacion activa, pasados como contexto crudo al LLM.
RECENT_MESSAGES_LIMIT = 8

SESSION_CACHE_TTL_SECONDS = 60 * 60  # 60 min de inactividad, ver documento fuente

_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        # protocol=2 (RESP2) a proposito: el redis-server local de este
        # proyecto es 5.0.14 (verificado), que no soporta RESP3 (requiere
        # Redis 6.0+). redis-py 5.x intenta RESP3 por defecto (comando
        # HELLO), que esta version de Redis rechaza con "unknown command
        # HELLO" -- sin este parametro, CUALQUIER operacion fallaria y el
        # cache caeria siempre a Postgres en silencio (funcional pero sin
        # el beneficio de performance que Redis deberia dar).
        #
        # socket_timeout/socket_connect_timeout explicitos (auditoria de
        # salud del backend, 2026-08-06, hallazgo M6): el try/except
        # generico que envuelve cada uso de este cliente (ver abajo)
        # protege contra un fallo RECHAZADO de Redis, pero no contra una
        # conexion que se queda COLGADA (sin timeout, el socket esperaria
        # indefinidamente y el except nunca se dispararia porque la llamada
        # nunca retorna) -- hoy Redis corre local asi que el riesgo es bajo
        # en la practica, pero si se despliega con Redis remoto esto podria
        # colgar el request completo.
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            protocol=2,
            socket_timeout=3,
            socket_connect_timeout=3,
        )
    return _redis_client


def _cache_key(conversation_id: int) -> str:
    return f"conversation:{conversation_id}:recent_messages"


def _load_from_postgres(db: Session, conversation_id: int, limit: int) -> list[dict]:
    messages = (
        db.query(Message)
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    messages.reverse()  # orden cronologico: el mas viejo primero, como espera el LLM
    return [{"role": m.role, "content": m.content} for m in messages]


def get_recent_history(
    db: Session, conversation_id: int, limit: int = RECENT_MESSAGES_LIMIT
) -> list[dict]:
    """Ultimos `limit` mensajes de la conversacion, en orden cronologico,
    listos para insertarse como turnos previos en los `messages` que se
    mandan al LLM (formato {"role": "user"|"assistant", "content": str}).

    Postgres es la fuente de verdad; Redis es solo un cache de lectura. Si
    Redis no esta disponible o falla por cualquier motivo, se cae a
    Postgres de forma silenciosa -- la correccion del sistema NUNCA depende
    de que Redis este arriba, tal como pide el documento fuente.
    """
    key = _cache_key(conversation_id)
    try:
        cached = _get_redis_client().get(key)
        if cached is not None:
            return json.loads(cached)
    except Exception:
        pass

    history = _load_from_postgres(db, conversation_id, limit)

    try:
        _get_redis_client().setex(key, SESSION_CACHE_TTL_SECONDS, json.dumps(history))
    except Exception:
        pass

    return history


def invalidate_history_cache(conversation_id: int) -> None:
    """Se llama despues de persistir un turno nuevo (user + assistant).

    Sin esto, la siguiente lectura devolveria el cache viejo SIN el turno
    que se acaba de guardar -- la conversacion "olvidaria" el ultimo
    intercambio cada dos turnos, peor que no tener cache. Se invalida en vez
    de actualizar el cache en el lugar para no arriesgar inconsistencias con
    escrituras concurrentes; la siguiente lectura recalcula desde Postgres
    (fuente de verdad) y repuebla el cache.
    """
    try:
        _get_redis_client().delete(_cache_key(conversation_id))
    except Exception:
        pass
