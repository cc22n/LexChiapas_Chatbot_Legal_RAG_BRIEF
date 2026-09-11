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
from app.models import Document, GoldenDatasetRun, GoldenDatasetRunCase
from app.rag.guardrails import OUT_OF_SCOPE_MESSAGE
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


@router.get("/metrics/usage", dependencies=[Depends(require_admin)])
def metrics_usage(db: Session = Depends(get_db)) -> dict:
    questions_per_day = db.execute(
        text(
            """
            SELECT date(created_at) AS day, count(*) AS count
            FROM messages
            WHERE role = 'user'
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
            """
        )
    ).mappings().all()

    unique_users_by_platform = db.execute(
        text(
            """
            SELECT platform, count(DISTINCT user_id) AS unique_users
            FROM conversations
            GROUP BY platform
            """
        )
    ).mappings().all()

    top_laws = db.execute(
        text(
            """
            SELECT elem->>'document_nombre' AS ley, count(*) AS mentions
            FROM messages, jsonb_array_elements(retrieved_chunks) AS elem
            WHERE role = 'assistant' AND retrieved_chunks IS NOT NULL
            GROUP BY ley
            ORDER BY mentions DESC
            LIMIT 10
            """
        )
    ).mappings().all()

    # Dedup EXACTO por texto de pregunta (no clustering semantico) -- cumple
    # el requisito #4 de LexChiapas_Dashboard_Metricas.md / WEB_FRONTEND_PLAN.md
    # Fase C.1 sin agregar dependencias nuevas.
    top_questions = db.execute(
        text(
            """
            SELECT content, count(*) AS count
            FROM messages
            WHERE role = 'user'
            GROUP BY content
            ORDER BY count DESC
            LIMIT 10
            """
        )
    ).mappings().all()

    conversations_by_platform = db.execute(
        text("SELECT platform, count(*) AS count FROM conversations GROUP BY platform")
    ).mappings().all()

    # questions_per_day_telegram / top_questions_telegram (LexChiapas_Plan_
    # Futuro.md item #7): mismas dos queries de arriba pero acotadas a
    # conversations.platform = 'telegram' via JOIN (messages NO tiene columna
    # platform propia). Nombre de campo _telegram explicito (no un shape
    # generico top_questions_by_platform con lista anidada por plataforma):
    # las variantes YA genericas de este archivo (unique_users_by_platform,
    # conversations_by_platform) son agregados triviales de una fila por
    # plataforma; top_questions/questions_per_day son consultas "top-N", y
    # generalizarlas a top-N-por-plataforma exige window functions
    # (ROW_NUMBER() OVER PARTITION BY platform) y anidar listas dentro de
    # cada elemento -- complejidad real para un caso con solo 2 plataformas
    # (telegram, web) donde el pedido concreto (item #7) es exclusivamente
    # "el equivalente al dashboard web pero para telegram". Sin un frontend
    # ya construido esperando el shape generico (a diferencia de AgentTrace/
    # laws), el campo explicito es el diseno mas simple que cumple el pedido
    # real; se puede migrar a un shape por-plataforma despues si aparece un
    # tercer canal real.
    questions_per_day_telegram = db.execute(
        text(
            """
            SELECT date(m.created_at) AS day, count(*) AS count
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.role = 'user' AND c.platform = 'telegram'
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
            """
        )
    ).mappings().all()

    top_questions_telegram = db.execute(
        text(
            """
            SELECT m.content AS content, count(*) AS count
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.role = 'user' AND c.platform = 'telegram'
            GROUP BY m.content
            ORDER BY count DESC
            LIMIT 10
            """
        )
    ).mappings().all()

    return {
        "questions_per_day": [dict(r) for r in questions_per_day],
        "unique_users_by_platform": [dict(r) for r in unique_users_by_platform],
        "top_laws": [dict(r) for r in top_laws],
        "top_questions": [dict(r) for r in top_questions],
        "conversations_by_platform": [dict(r) for r in conversations_by_platform],
        "questions_per_day_telegram": [dict(r) for r in questions_per_day_telegram],
        "top_questions_telegram": [dict(r) for r in top_questions_telegram],
    }


@router.get("/metrics/quality", dependencies=[Depends(require_admin)])
def metrics_quality(db: Session = Depends(get_db)) -> dict:
    not_found_rate = db.execute(
        text(
            """
            SELECT
              count(*) FILTER (WHERE found_answer = false) AS not_found,
              count(*) FILTER (WHERE found_answer IS NOT NULL) AS total
            FROM messages
            WHERE role = 'assistant'
            """
        )
    ).mappings().one()

    feedback_ratio = db.execute(
        text("SELECT rating, count(*) AS count FROM feedback GROUP BY rating")
    ).mappings().all()

    # feedback_ratio_telegram (LexChiapas_Plan_Futuro.md item #7): mismo
    # agrupado por rating de arriba, pero acotado a feedback de mensajes de
    # conversaciones de telegram. feedback no tiene platform ni conversation_id
    # directo -- hay que subir 2 niveles: feedback.message_id -> messages.id
    # -> messages.conversation_id -> conversations.id -> conversations.platform.
    # Campo _telegram explicito por la misma razon que arriba (top_questions_
    # telegram): feedback_ratio ya es un agregado de una fila por rating,
    # generalizarlo a "por plataforma" es trivial de agregar despues (mismo
    # GROUP BY platform, rating) si un tercer canal real lo justifica, pero
    # hoy solo hace falta separar telegram del resto.
    feedback_ratio_telegram = db.execute(
        text(
            """
            SELECT f.rating AS rating, count(*) AS count
            FROM feedback f
            JOIN messages m ON m.id = f.message_id
            JOIN conversations c ON c.id = m.conversation_id
            WHERE c.platform = 'telegram'
            GROUP BY f.rating
            """
        )
    ).mappings().all()

    top_cited_articles = db.execute(
        text(
            """
            SELECT elem->>'document_nombre' AS ley, elem->>'articulo_numero' AS articulo, count(*) AS mentions
            FROM messages, jsonb_array_elements(retrieved_chunks) AS elem
            WHERE role = 'assistant' AND found_answer = true
            GROUP BY ley, articulo
            ORDER BY mentions DESC
            LIMIT 10
            """
        )
    ).mappings().all()

    # avg_similarity_grounded / similarity_histogram (deseables #10/#11 de
    # LexChiapas_Dashboard_Metricas.md / WEB_FRONTEND_PLAN.md Fase C.1):
    # SOLO sobre chunks marcados passed_threshold=true en el JSONB -- un
    # chunk que solo vino de BM25 (sparse) normaliza su similarity a 1.0 sin
    # ser comparable a similitud coseno real (ver
    # app.rag.retriever.RetrievedChunk.passed_threshold), mezclarlo
    # engañaria el promedio/histograma. Nota: mensajes persistidos ANTES de
    # este cambio no tienen "passed_threshold" en su JSONB -- el operador
    # ->> devuelve NULL para esa clave inexistente, ::boolean de NULL es
    # NULL, y NULL = true es NULL (no true), asi que esas filas quedan
    # excluidas naturalmente del WHERE. Eso es correcto, no un bug: no hay
    # forma de saber retroactivamente si esos chunks viejos pasaron
    # threshold real o no.
    avg_similarity_grounded = db.execute(
        text(
            """
            SELECT avg((elem->>'similarity')::float) AS avg_similarity
            FROM messages, jsonb_array_elements(retrieved_chunks) AS elem
            WHERE role = 'assistant'
              AND retrieved_chunks IS NOT NULL
              AND (elem->>'passed_threshold')::boolean = true
            """
        )
    ).scalar_one()

    # Buckets fijos de 0.1 (0.5-0.6 ... 0.9-1.0), etiquetados explicitamente
    # en vez de un indice numerico de width_bucket() -- mas legible para el
    # frontend y coincide exacto con lo pedido (LexChiapas_Dashboard_
    # Metricas.md deseable #11). El limite superior de cada bucket es
    # exclusivo salvo el ultimo ("0.9-1.0", que es el ELSE de abajo e
    # incluye similarity=1.0 exacto).
    similarity_histogram = db.execute(
        text(
            """
            WITH grounded_similarities AS (
              SELECT (elem->>'similarity')::float AS similarity
              FROM messages, jsonb_array_elements(retrieved_chunks) AS elem
              WHERE role = 'assistant'
                AND retrieved_chunks IS NOT NULL
                AND (elem->>'passed_threshold')::boolean = true
            )
            SELECT bucket_range AS range, count(*) AS count
            FROM grounded_similarities,
                 LATERAL (
                   SELECT CASE
                     WHEN similarity < 0.6 THEN '0.5-0.6'
                     WHEN similarity < 0.7 THEN '0.6-0.7'
                     WHEN similarity < 0.8 THEN '0.7-0.8'
                     WHEN similarity < 0.9 THEN '0.8-0.9'
                     ELSE '0.9-1.0'
                   END AS bucket_range
                 ) b
            GROUP BY bucket_range
            ORDER BY bucket_range
            """
        )
    ).mappings().all()

    # grounded_by_rewrite (WEB_FRONTEND_PLAN.md Fase E): agrupa por
    # was_rewritten para medir si el query rewriting (app.rag.query_rewriting)
    # correlaciona con mas respuestas fundamentadas. Solo mensajes que
    # PASARON por esa decision (was_rewritten IS NOT NULL) -- excluye la
    # ruta agentica (siempre NULL, no hace rewriting, ver docstring de
    # Message.was_rewritten) y los mensajes de error del camino de excepcion
    # de conversation_store.handle_turn (found_answer=None ahi, tampoco
    # corrieron rewriting de verdad).
    grounded_by_rewrite = db.execute(
        text(
            """
            SELECT
              was_rewritten,
              count(*) FILTER (WHERE found_answer = true) AS grounded,
              count(*) AS total
            FROM messages
            WHERE role = 'assistant' AND was_rewritten IS NOT NULL
            GROUP BY was_rewritten
            ORDER BY was_rewritten
            """
        )
    ).mappings().all()

    return {
        "not_found_rate": dict(not_found_rate),
        "feedback_ratio": [dict(r) for r in feedback_ratio],
        "feedback_ratio_telegram": [dict(r) for r in feedback_ratio_telegram],
        "top_cited_articles": [dict(r) for r in top_cited_articles],
        "avg_similarity_grounded": avg_similarity_grounded,
        "similarity_histogram": [dict(r) for r in similarity_histogram],
        "grounded_by_rewrite": [dict(r) for r in grounded_by_rewrite],
    }


@router.get("/metrics/performance", dependencies=[Depends(require_admin)])
def metrics_performance(db: Session = Depends(get_db)) -> dict:
    latency = db.execute(
        text(
            """
            SELECT
              avg(response_time_ms) AS avg_ms,
              percentile_cont(0.95) WITHIN GROUP (ORDER BY response_time_ms) AS p95_ms
            FROM messages
            WHERE role = 'assistant' AND response_time_ms IS NOT NULL
            """
        )
    ).mappings().one()

    # latency_breakdown (item 3.2 de WEB_FRONTEND_PLAN.md Fase C.2): solo
    # existe en mensajes que pasaron por app.rag.rag_pipeline.answer_question
    # de verdad (no cache hit, no pipeline agentico) -- ver
    # app.models.message.Message.search_time_ms para el detalle de que cubre
    # cada campo. avg()/percentile_cont() ignoran NULL automaticamente, asi
    # que mensajes viejos (de antes de este cambio) o cache hits quedan
    # excluidos solos, sin filtro WHERE extra.
    latency_breakdown = db.execute(
        text(
            """
            SELECT
              avg(search_time_ms) AS avg_search_ms,
              percentile_cont(0.95) WITHIN GROUP (ORDER BY search_time_ms) AS p95_search_ms,
              avg(generation_time_ms) AS avg_generation_ms,
              percentile_cont(0.95) WITHIN GROUP (ORDER BY generation_time_ms) AS p95_generation_ms
            FROM messages
            WHERE role = 'assistant'
            """
        )
    ).mappings().one()

    usage_by_model = db.execute(
        text(
            """
            SELECT llm_model, count(*) AS count
            FROM messages
            WHERE role = 'assistant' AND llm_model IS NOT NULL
            GROUP BY llm_model
            ORDER BY count DESC
            """
        )
    ).mappings().all()

    tokens_per_day = db.execute(
        text(
            """
            SELECT date(created_at) AS day, sum(prompt_tokens) AS prompt_tokens, sum(completion_tokens) AS completion_tokens
            FROM messages
            WHERE role = 'assistant'
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
            """
        )
    ).mappings().all()

    recent_ingestion_errors = db.execute(
        text(
            """
            SELECT id, document_id, status, error_message, started_at, completed_at
            FROM ingestion_logs
            WHERE status = 'failed'
            ORDER BY started_at DESC NULLS LAST
            LIMIT 20
            """
        )
    ).mappings().all()

    # recent_chat_errors (item 14 "Errores del sistema" de
    # LexChiapas_Dashboard_Metricas.md / WEB_FRONTEND_PLAN.md Fase C.1, gap
    # senalado al corregir esa fila: system_error_rate ya daba el conteo
    # agregado pero no un listado navegable, mismo patron que
    # recent_ingestion_errors arriba). found_answer IS NULL identifica un
    # turno donde el pipeline trueno con una excepcion real (ver
    # app.bots.conversation_store.handle_turn) -- error_message trae el
    # traceback completo persistido ahi.
    recent_chat_errors = db.execute(
        text(
            """
            SELECT id, conversation_id, error_message, created_at
            FROM messages
            WHERE role = 'assistant' AND found_answer IS NULL
            ORDER BY created_at DESC
            LIMIT 20
            """
        )
    ).mappings().all()

    # system_error_rate: distinto de not_found_rate (metrics/quality), que
    # ya excluye found_answer IS NULL correctamente -- esa es la fuente de
    # verdad de "no encontrado" legitimo del RAG. Este conteo es sobre el
    # OTRO caso: found_answer IS NULL significa que el pipeline trueno con
    # una excepcion real ANTES de poder decidir grounded/no-grounded (ver
    # app.bots.conversation_store.handle_turn, error_message), no que el RAG
    # busco de verdad y no encontro nada.
    system_error_rate = db.execute(
        text(
            """
            SELECT
              count(*) FILTER (WHERE found_answer IS NULL) AS system_errors,
              count(*) AS total
            FROM messages
            WHERE role = 'assistant'
            """
        )
    ).mappings().one()

    # primary_vs_fallback (item 3.1 de WEB_FRONTEND_PLAN.md Fase C.2): no
    # requiere columna ni dato nuevo -- llm_model ya guarda que modelo
    # respondio de verdad, "primario" es solo compararlo contra
    # fallback_order[0] de ai_config.json AHORA, no algo que haga falta
    # capturar en el momento de generar. Se calcula en Python sobre
    # usage_by_model (ya trae el conteo por modelo) en vez de otra query.
    primary_model = get_primary_model()
    primary_count = sum(r["count"] for r in usage_by_model if r["llm_model"] == primary_model)
    fallback_count = sum(r["count"] for r in usage_by_model if r["llm_model"] != primary_model)
    primary_vs_fallback = {
        "primary_model": primary_model,
        "primary_count": primary_count,
        "fallback_count": fallback_count,
    }

    return {
        "latency": dict(latency),
        "latency_breakdown": dict(latency_breakdown),
        "usage_by_model": [dict(r) for r in usage_by_model],
        "tokens_per_day": [dict(r) for r in tokens_per_day],
        "recent_ingestion_errors": [dict(r) for r in recent_ingestion_errors],
        "recent_chat_errors": [dict(r) for r in recent_chat_errors],
        "system_error_rate": dict(system_error_rate),
        "primary_vs_fallback": primary_vs_fallback,
    }


@router.get("/metrics/guardrails", dependencies=[Depends(require_admin)])
def metrics_guardrails(db: Session = Depends(get_db)) -> dict:
    # Compara contra el texto exacto de OUT_OF_SCOPE_MESSAGE (app/rag/guardrails.py)
    # porque Capa 1 no marca los mensajes con ningun flag propio en la DB --
    # es la misma comparacion que ya usa app/api/chat_web.py para el campo
    # out_of_scope. Los intentos de jailbreak (detect_jailbreak_attempt) ya
    # se persisten (columna messages.jailbreak_detected, poblada en
    # app.bots.conversation_store.handle_turn sobre el mensaje role='user'),
    # asi que jailbreak_attempts abajo ya es un conteo real, no un placeholder.
    out_of_scope_per_day = db.execute(
        text(
            """
            SELECT date(created_at) AS day, count(*) AS count
            FROM messages
            WHERE role = 'assistant' AND content = :out_of_scope_message
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
            """
        ),
        {"out_of_scope_message": OUT_OF_SCOPE_MESSAGE},
    ).mappings().all()

    total_out_of_scope = db.execute(
        text(
            """
            SELECT count(*) AS count
            FROM messages
            WHERE role = 'assistant' AND content = :out_of_scope_message
            """
        ),
        {"out_of_scope_message": OUT_OF_SCOPE_MESSAGE},
    ).scalar_one()

    jailbreak_attempts = db.execute(
        text("SELECT count(*) FROM messages WHERE jailbreak_detected = true")
    ).scalar_one()

    return {
        "out_of_scope_per_day": [dict(r) for r in out_of_scope_per_day],
        "total_out_of_scope": total_out_of_scope,
        "jailbreak_attempts": jailbreak_attempts,
    }


@router.get("/metrics/agent", dependencies=[Depends(require_admin)])
def metrics_agent(db: Session = Depends(get_db)) -> dict:
    """Metricas de la ruta agentica (app.rag.agent_pipeline.
    answer_question_agentic) -- solo considera mensajes que de verdad
    pasaron por ahi (agent_trace IS NOT NULL, ver Message.agent_trace).
    Si ai_config.json "agentic_rag.enabled" nunca estuvo en true, esto
    viene vacio/en 0 -- no es un error, es honesto (WEB_FRONTEND_PLAN.md
    Fase F)."""
    route_distribution = db.execute(
        text(
            """
            SELECT agent_trace->>'route' AS route, count(*) AS count
            FROM messages
            WHERE role = 'assistant' AND agent_trace IS NOT NULL
            GROUP BY route
            ORDER BY count DESC
            """
        )
    ).mappings().all()

    avg_intentos = db.execute(
        text(
            """
            SELECT avg((agent_trace->>'intentos')::int) AS avg_intentos
            FROM messages
            WHERE role = 'assistant' AND agent_trace IS NOT NULL
            """
        )
    ).scalar_one()

    self_reflection_trigger_rate = db.execute(
        text(
            """
            SELECT
              count(*) FILTER (WHERE (agent_trace->>'self_reflection_triggered')::boolean = true) AS triggered,
              count(*) AS total
            FROM messages
            WHERE role = 'assistant' AND agent_trace IS NOT NULL
            """
        )
    ).mappings().one()

    return {
        "route_distribution": [dict(r) for r in route_distribution],
        "avg_intentos": avg_intentos,
        "self_reflection_trigger_rate": dict(self_reflection_trigger_rate),
    }


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


def _golden_run_summary(run: GoldenDatasetRun) -> dict:
    return {
        "id": run.id,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "total": run.total,
        "passed": run.passed,
        "xfailed_known": run.xfailed_known,
        "failed": run.failed,
        "duration_ms": run.duration_ms,
    }


@router.get("/metrics/golden_dataset", dependencies=[Depends(require_admin)])
def metrics_golden_dataset(db: Session = Depends(get_db)) -> dict:
    """Corrida MAS RECIENTE del golden dataset real (con su detalle por
    caso, ver GoldenDatasetRunCase) + las ultimas 10 corridas para graficar
    tendencia en el dashboard (WEB_FRONTEND_PLAN.md seccion 3.3, item 5).
    Reemplaza el snapshot manual estatico (ragAdvancedSnapshot.ts, Fase E)
    con dato real en vivo.

    Si todavia no corrio ninguna evaluacion (tabla vacia), devuelve una
    forma explicita {"latest": None, "history": []} en vez de un error --
    el frontend puede distinguir "sin datos" de una falla real."""
    latest_run = (
        db.query(GoldenDatasetRun).order_by(GoldenDatasetRun.started_at.desc()).first()
    )
    if latest_run is None:
        return {"latest": None, "history": []}

    cases = (
        db.query(GoldenDatasetRunCase)
        .filter(GoldenDatasetRunCase.run_id == latest_run.id)
        .order_by(GoldenDatasetRunCase.id)
        .all()
    )

    history = (
        db.query(GoldenDatasetRun)
        .order_by(GoldenDatasetRun.started_at.desc())
        .limit(10)
        .all()
    )

    latest = _golden_run_summary(latest_run)
    latest["cases"] = [
        {
            "id": c.id,
            "pregunta": c.pregunta,
            "passed": c.passed,
            "expects_grounded": c.expects_grounded,
            "actual_grounded": c.actual_grounded,
            "articulo_esperado": c.articulo_esperado,
            "posicion_encontrada": c.posicion_encontrada,
            "respuesta_snippet": c.respuesta_snippet,
        }
        for c in cases
    ]

    return {
        "latest": latest,
        "history": [_golden_run_summary(r) for r in history],
    }
