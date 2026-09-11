import logging
import time

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.database import SessionLocal
from app.llm.providers import embed_text

router = APIRouter(tags=["health"])
logger = logging.getLogger("lexchiapas.health")

# Canario de embeddings cacheado por proceso (Fase 9.8/A6). NO se llama a
# NVIDIA en cada probe de readiness (el orquestador puede pegarle cada pocos
# segundos): se guarda el ultimo veredicto y solo se refresca cuando expiro el
# TTL, con el mismo patron de cache-por-proceso que _compiled_graphs en
# app.rag.agent_pipeline (global + time.monotonic()). No usa Redis a proposito
# -- readiness no debe acoplarse a Redis (ver comentario en health_ready).
_EMBED_CANARY_TTL_SECONDS = 60.0
_embed_canary: tuple[float, bool] | None = None  # (monotonic_ts, ok)


def _embeddings_ok() -> bool:
    """True si el modelo de embeddings responde. Resultado cacheado
    _EMBED_CANARY_TTL_SECONDS para no gastar una llamada real por probe."""
    global _embed_canary
    now = time.monotonic()
    if _embed_canary is not None and (now - _embed_canary[0]) < _EMBED_CANARY_TTL_SECONDS:
        return _embed_canary[1]
    try:
        embed_text("ping")
        ok = True
    except Exception as exc:  # noqa: BLE001 - cualquier fallo = no listo para RAG
        logger.warning("health/ready: canario de embeddings fallo: %s: %s", type(exc).__name__, exc)
        ok = False
    _embed_canary = (now, ok)
    return ok


@router.get("/health")
def health() -> dict:
    """Liveness: el proceso esta vivo y puede responder HTTP. NO verifica
    dependencias externas a proposito (tiene que ser rapido e incondicional
    -- ver /health/ready para eso)."""
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready(response: Response) -> dict:
    """Readiness: ademas de estar vivo, puede de verdad atender requests
    reales -- confirma que Postgres responde Y que el modelo de embeddings
    esta vivo.

    BUG REAL corregido (auditoria de salud del backend, 2026-08-06, hallazgo
    M3): antes solo existia /health, que devolvia 200 incondicional aunque
    la DB estuviera caida o el pool agotado -- si el hosting usa un
    healthcheck para decidir reinicios/routing, no detectaria el problema
    real mientras TODOS los endpoints reales (chat, webhook, admin) ya
    estarian fallando con 500. Solo verifica Postgres (no Redis: ya es
    best-effort/opcional en todo el resto del codigo, un Redis caido no
    deberia tumbar el readiness).

    Fase 9.8/A6: se agrega el canario de embeddings. Sin esto, /health/ready
    devolvia 200 aunque el modelo de embeddings estuviera muerto (410, el
    incidente real de la Fase 9.7) y TODO turno de RAG estuviera fallando --
    exactamente el modo de fallo que readiness debe reflejar. Si no se puede
    embeber, la instancia NO esta lista para su funcion principal, asi que se
    responde 503. Trade-off aceptado y honesto: si el modelo esta muerto a
    nivel plataforma, todas las instancias quedan 'unhealthy' en el
    orquestador (que es la senal correcta -- el servicio ESTA caido hasta que
    un humano cambie embeddings.model); liveness /health sigue en 200 asi que
    no hay crash-loop. El canario esta cacheado (TTL) para no encarecer los
    probes ni flapear ante un blip transitorio (embed_text ya reintenta 429/5xx).
    """
    postgres_ok = True
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("health/ready: Postgres no responde: %s", exc)
        postgres_ok = False
    finally:
        db.close()

    embeddings_ok = _embeddings_ok()

    if not postgres_ok or not embeddings_ok:
        response.status_code = 503
    return {
        "status": "ok" if (postgres_ok and embeddings_ok) else "not ready",
        "postgres": "ok" if postgres_ok else "down",
        "embeddings": "ok" if embeddings_ok else "down",
    }
