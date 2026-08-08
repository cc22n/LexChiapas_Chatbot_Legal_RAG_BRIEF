import logging

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.database import SessionLocal

router = APIRouter(tags=["health"])
logger = logging.getLogger("lexchiapas.health")


@router.get("/health")
def health() -> dict:
    """Liveness: el proceso esta vivo y puede responder HTTP. NO verifica
    dependencias externas a proposito (tiene que ser rapido e incondicional
    -- ver /health/ready para eso)."""
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready(response: Response) -> dict:
    """Readiness: ademas de estar vivo, puede de verdad atender requests
    reales -- confirma que Postgres responde.

    BUG REAL corregido (auditoria de salud del backend, 2026-08-06, hallazgo
    M3): antes solo existia /health, que devolvia 200 incondicional aunque
    la DB estuviera caida o el pool agotado -- si el hosting usa un
    healthcheck para decidir reinicios/routing, no detectaria el problema
    real mientras TODOS los endpoints reales (chat, webhook, admin) ya
    estarian fallando con 500. Solo verifica Postgres (no Redis: ya es
    best-effort/opcional en todo el resto del codigo, un Redis caido no
    deberia tumbar el readiness).
    """
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("health/ready: Postgres no responde: %s", exc)
        response.status_code = 503
        return {"status": "not ready"}
    finally:
        db.close()
