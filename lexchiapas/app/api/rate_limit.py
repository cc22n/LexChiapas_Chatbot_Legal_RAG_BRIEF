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


def enforce_rate_limit(session_id: str) -> None:
    now = time.monotonic()
    timestamps = _requests_by_session[session_id]

    while timestamps and now - timestamps[0] > WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiadas preguntas seguidas, espera un momento (limite: {MAX_REQUESTS_PER_WINDOW} por minuto).",
        )

    timestamps.append(now)
