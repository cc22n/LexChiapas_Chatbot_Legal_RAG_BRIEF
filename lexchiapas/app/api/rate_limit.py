import time
from collections import defaultdict, deque

from fastapi import HTTPException

# Limitador en memoria por sesion, ventana deslizante simple. Suficiente para
# un solo proceso de Uvicorn (uso personal/portafolio); NO es correcto contra
# multiples workers/procesos (cada uno tendria su propio contador). Si se
# despliega con mas de 1 worker, mover esto a Redis (ya esta cableado como
# broker de Celery, se podria reusar).
WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 10

_requests_by_session: dict[str, deque[float]] = defaultdict(deque)

# BUG REAL (2026-08-04, revision de seguridad, hallazgo #7): un defaultdict
# nunca borra una clave sola -- cada session_id/IP distinto que se vio
# ALGUNA VEZ se queda en el dict para siempre, incluso despues de que sus
# timestamps expiraron (el `while` de abajo solo vacia el deque interno, no
# borra la entrada del dict). Bajo trafico normal de un chat publico (mas
# ahora que enforce_rate_limit se llama 2 veces por request, ver
# chat_web.py), esto es un memory leak lento. Se barre cada
# SWEEP_EVERY_N_CALLS llamadas (no en cada una) para no pagar el costo de
# iterar todo el dict en el hot path de cada request.
SWEEP_EVERY_N_CALLS = 500
_calls_since_sweep = 0


def _sweep_expired(now: float) -> None:
    stale_keys = [
        key
        for key, timestamps in _requests_by_session.items()
        if not timestamps or now - timestamps[-1] > WINDOW_SECONDS
    ]
    for key in stale_keys:
        del _requests_by_session[key]


def enforce_rate_limit(key: str) -> None:
    """`key` es cualquier identificador de bucket (session_id, "ip:<addr>",
    etc.) -- ver chat_web.py, que llama esto dos veces por request (una por
    session_id, una por IP) para que un cliente no pueda saltarse el limite
    solo mandando un session_id nuevo por request (BUG REAL encontrado
    2026-08-04: session_id lo manda el cliente en el body sin ningun amarre
    al servidor, asi que antes de este fix el limite de 10/min era trivial
    de evadir -- cada pregunta puede encadenar hasta 5 llamadas LLM reales
    en el pipeline, exposicion real de costo). El bucket por IP no es
    perfecto (varios usuarios detras del mismo NAT/proxy comparten IP), pero
    cierra el bypass trivial sin requerir autenticacion real."""
    global _calls_since_sweep
    now = time.monotonic()
    timestamps = _requests_by_session[key]

    while timestamps and now - timestamps[0] > WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiadas preguntas seguidas, espera un momento (limite: {MAX_REQUESTS_PER_WINDOW} por minuto).",
        )

    timestamps.append(now)

    _calls_since_sweep += 1
    if _calls_since_sweep >= SWEEP_EVERY_N_CALLS:
        _calls_since_sweep = 0
        _sweep_expired(now)
