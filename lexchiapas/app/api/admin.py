import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.admin_auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_cookie,
    require_admin,
    revoke_session,
)
from app.api.rate_limit import enforce_rate_limit
from app.config import get_settings, reload_ai_config
from app.database import get_db
from app.llm.router import get_primary_model
from app.models import Document
from app.repositories.admin_metrics import agent_metrics, golden_dataset_metrics, guardrails_metrics, performance_metrics, quality_metrics, usage_metrics
from app.schemas.admin_metrics import AgentMetrics, GoldenDatasetMetrics, GuardrailsMetrics, PerformanceMetrics, QualityMetrics, UsageMetrics
from app.schemas.document import DocumentCreate, DocumentOut
from app.workers.evaluation_tasks import run_golden_dataset_task

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


class AdminLoginRequest(BaseModel):
    admin_api_key: str


@router.post("/login")
def admin_login(payload: AdminLoginRequest, request: Request, response: Response) -> dict:
    # Mitigacion de fuerza bruta (ver PLAN.md Fase 4, hallazgo documentado a
    # proposito sin corregir hasta ahora): reusa app.api.rate_limit, ya usado
    # en chat_web.py/telegram_bot.py, esta vez con el IP del cliente como
    # clave en vez de session_id (no hay sesion todavia, es el propio intento
    # de crearla). Se aplica ANTES de revisar la key para que tambien
    # throttle los intentos que SI adivinan la key.
    client_host = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"admin_login:{client_host}")

    # BUG REAL (2026-08-04, revision de seguridad): comparacion con `!=` en
    # vez de hmac.compare_digest -- mismo hallazgo ya corregido en
    # admin_auth.py:require_admin, encontrado tambien aca al revisar CORS.
    if not settings.admin_api_key or not hmac.compare_digest(
        payload.admin_api_key, settings.admin_api_key
    ):
        raise HTTPException(status_code=401, detail="invalid admin api key")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_cookie(),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        # A3: Secure fuera de development (en local es HTTP, un Secure ahi
        # impediria que la cookie viaje y romperia el login). En prod el
        # deploy sirve por HTTPS, asi que la cookie de sesion admin nunca
        # debe viajar en claro.
        secure=settings.environment != "development",
    )
    return {"ok": True}


@router.post("/logout")
def admin_logout(request: Request, response: Response) -> dict:
    # Fase 9.8 (pentest MEDIA): ademas de borrar la cookie del navegador, se
    # revoca server-side (blocklist en Redis) para que un valor de cookie ya
    # copiado deje de ser aceptado por require_admin.
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if session_cookie:
        revoke_session(session_cookie)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@router.post("/config/reload", dependencies=[Depends(require_admin)])
def admin_reload_config() -> dict:
    """Recarga ai_config.json sin reiniciar el proceso (Fase 9.8/C2). Util
    tras editar el archivo en un incidente -- ej. cambiar embeddings.model
    cuando el actual muere (410), sin necesidad de un restart que corte el
    servicio. get_ai_config() esta bajo @lru_cache; esto solo limpia ese
    cache."""
    reload_ai_config()
    return {"ok": True, "reloaded": "ai_config.json"}


@router.get("/documents", response_model=list[DocumentOut], dependencies=[Depends(require_admin)])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).order_by(Document.id).all()


@router.post("/documents", response_model=DocumentOut, dependencies=[Depends(require_admin)])
def create_document(payload: DocumentCreate, db: Session = Depends(get_db)) -> Document:
    document = Document(**payload.model_dump())
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.delete("/documents/{document_id}", dependencies=[Depends(require_admin)])
def deactivate_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    document.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/metrics/usage", response_model=UsageMetrics, dependencies=[Depends(require_admin)])
def metrics_usage(db: Session = Depends(get_db)) -> dict:
    return usage_metrics(db)


@router.get("/metrics/quality", response_model=QualityMetrics, dependencies=[Depends(require_admin)])
def metrics_quality(db: Session = Depends(get_db)) -> dict:
    return quality_metrics(db)


@router.get("/metrics/performance", response_model=PerformanceMetrics, dependencies=[Depends(require_admin)])
def metrics_performance(db: Session = Depends(get_db)) -> dict:
    return performance_metrics(db)


@router.get("/metrics/guardrails", response_model=GuardrailsMetrics, dependencies=[Depends(require_admin)])
def metrics_guardrails(db: Session = Depends(get_db)) -> dict:
    return guardrails_metrics(db)


@router.get("/metrics/agent", response_model=AgentMetrics, dependencies=[Depends(require_admin)])
def metrics_agent(db: Session = Depends(get_db)) -> dict:
    return agent_metrics(db)


@router.post("/evaluation/run", dependencies=[Depends(require_admin)])
def trigger_golden_dataset_run() -> dict:
    """Encola la corrida completa del golden dataset real (24 preguntas, ver
    app.evaluation.golden_dataset, ~35 minutos y llamadas reales de API) via
    Celery -- devuelve el task_id de inmediato, NO espera el resultado
    (WEB_FRONTEND_PLAN.md seccion 3.3, item 4: ese tiempo excede cualquier
    timeout razonable de un endpoint HTTP). El resultado final se consulta
    despues con GET /admin/metrics/golden_dataset."""
    task = run_golden_dataset_task.delay()
    return {"task_id": task.id}


@router.get("/metrics/golden_dataset", response_model=GoldenDatasetMetrics, dependencies=[Depends(require_admin)])
def metrics_golden_dataset(db: Session = Depends(get_db)) -> dict:
    """Corrida mas reciente del golden dataset (con detalle por caso) y las
    ultimas 10 para la tendencia. Sin corridas: {"latest": None, "history": []}."""
    return golden_dataset_metrics(db)
