import redis
import kombu.transport.redis as _kombu_redis
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from app.config import get_settings

# Fase 4, hallazgo real: el redis-server local de este proyecto es 5.0.14
# (verificado con INFO server -- ver tambien app/rag/memory.py, que ya
# documenta el mismo root cause para el uso directo del cliente). redis-py
# 6+ intenta negociar RESP3 por defecto (comando HELLO al conectar), que
# Redis 5.0.14 rechaza con "unknown command HELLO" -- confirmado en vivo,
# tanto para un cliente directo como para `celery -A ... worker` (el
# consumer nunca lograba conectar al broker, reintentando indefinidamente).
# app/rag/memory.py ya resuelve esto para el uso directo pasando
# `protocol=2` al construir el cliente -- pero kombu (el transporte de
# Celery) construye `redis.Connection` DIRECTO via un connection pool,
# sin exponer un `protocol` en `broker_transport_options` (no esta en la
# lista blanca `Channel.from_transport_options` de kombu 5.6). Se resuelve
# con una subclase minima que fuerza protocol=2 si no se especifica, y se
# registra como `connection_class` del canal de kombu ANTES de construir
# la app de Celery.
#
# Nota aparte, tambien verificada en vivo: `redis-py` 6+ agrega una
# funcion nueva ("maintenance notifications", para Redis Enterprise) que
# truena con un error DISTINTO ("Maintenance notifications are only
# supported with hiredis and RESP3 parsers!") especificamente en el camino
# de kombu, incluso con protocol=2 forzado -- por eso requirements.txt fija
# `redis>=5.0,<6.0` (la generacion 5.x, sin esa funcion, funciona limpio
# con ambos usos -- directo y via Celery).
class _Resp2Connection(redis.Connection):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("protocol", 2)
        super().__init__(*args, **kwargs)


_kombu_redis.Transport.Channel.connection_class = _Resp2Connection

settings = get_settings()

celery_app = Celery(
    "lexchiapas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.ingestion_tasks",
        "app.workers.update_tasks",
        "app.workers.evaluation_tasks",
        "app.workers.alerting_tasks",
    ],
)


# A7 (auditoria 2026-09-09): bajo el modelo prefork de Celery, cada proceso
# worker es un fork del padre y HEREDA el engine/pool de SQLAlchemy creado a
# nivel de modulo en app.database -- las conexiones TCP a Postgres quedan
# compartidas entre procesos, produciendo errores intermitentes ("SSL error",
# "connection already closed") indistinguibles de un bug de aplicacion. El
# fix estandar: descartar el pool heredado al arrancar cada worker, para que
# cada proceso abra sus PROPIAS conexiones de forma perezosa.
@worker_process_init.connect
def _dispose_inherited_engine(**_kwargs) -> None:
    from app.database import engine

    engine.dispose()

# app.workers.evaluation_tasks.run_golden_dataset_task (WEB_FRONTEND_PLAN.md
# seccion 3.3) a proposito NO tiene entrada aca -- disparo manual unicamente
# via POST /admin/evaluation/run, nunca automatico. Correrla cada noche
# gastaria API real (~35 min, NVIDIA NIM/OpenAI/xAI) sin que el pipeline
# haya cambiado.
celery_app.conf.beat_schedule = {
    "actualizar-leyes-diario": {
        "task": "app.workers.update_tasks.check_for_law_updates",
        "schedule": crontab(hour=3, minute=0),
    },
    # Fase 9.8/C3: canario de salud cada 5 min (embeddings + pico de errores
    # de sistema) -> alerta a Telegram. Barato (1 llamada de embeddings por
    # tick) y sin dependencias de pago.
    "canario-salud-5min": {
        "task": "app.workers.alerting_tasks.health_canary",
        "schedule": crontab(minute="*/5"),
    },
}
celery_app.conf.timezone = "America/Mexico_City"
