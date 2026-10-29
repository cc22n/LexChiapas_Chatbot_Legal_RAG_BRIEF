"""Consultas de las metricas del panel de administracion (/admin/metrics/*).

Cada funcion devuelve un dict listo para validarse contra el esquema de
app.schemas.admin_metrics; el SQL no cambia al mover las consultas aca.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.llm.router import get_primary_model


def _rows(db: Session, sql: str) -> list[dict]:
    return [dict(r) for r in db.execute(text(sql)).mappings().all()]


def usage_metrics(db: Session) -> dict:
    # questions_per_day_telegram / top_questions_telegram: las mismas dos
    # consultas de uso acotadas a conversations.platform = 'telegram' via JOIN
    # (messages no tiene columna platform propia). top_questions es un dedup
    # EXACTO por texto de pregunta, no clustering semantico.
    return {
        "questions_per_day": _rows(
            db,
            """
            SELECT date(created_at) AS day, count(*) AS count
            FROM messages
            WHERE role = 'user'
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
            """,
        ),
        "unique_users_by_platform": _rows(
            db,
            """
            SELECT platform, count(DISTINCT user_id) AS unique_users
            FROM conversations
            GROUP BY platform
            """,
        ),
        "top_laws": _rows(
            db,
            """
            SELECT elem->>'document_nombre' AS ley, count(*) AS mentions
            FROM messages, jsonb_array_elements(retrieved_chunks) AS elem
            WHERE role = 'assistant' AND retrieved_chunks IS NOT NULL
            GROUP BY ley
            ORDER BY mentions DESC
            LIMIT 10
            """,
        ),
        "top_questions": _rows(
            db,
            """
            SELECT content, count(*) AS count
            FROM messages
            WHERE role = 'user'
            GROUP BY content
            ORDER BY count DESC
            LIMIT 10
            """,
        ),
        "conversations_by_platform": _rows(
            db, "SELECT platform, count(*) AS count FROM conversations GROUP BY platform"
        ),
        "questions_per_day_telegram": _rows(
            db,
            """
            SELECT date(m.created_at) AS day, count(*) AS count
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.role = 'user' AND c.platform = 'telegram'
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
            """,
        ),
        "top_questions_telegram": _rows(
            db,
            """
            SELECT m.content AS content, count(*) AS count
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.role = 'user' AND c.platform = 'telegram'
            GROUP BY m.content
            ORDER BY count DESC
            LIMIT 10
            """,
        ),
    }


def quality_metrics(db: Session) -> dict:
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


def performance_metrics(db: Session) -> dict:
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

    # Fase 9.8/A10: ademas de los tokens de generacion, se suman los
    # auxiliares (decidir/reformular/grounding/rewrite) y un total real. Las
    # claves prompt_tokens/completion_tokens se conservan para no romper el
    # dashboard existente.
    tokens_per_day = db.execute(
        text(
            """
            SELECT date(created_at) AS day,
                   sum(prompt_tokens) AS prompt_tokens,
                   sum(completion_tokens) AS completion_tokens,
                   sum(aux_prompt_tokens) AS aux_prompt_tokens,
                   sum(aux_completion_tokens) AS aux_completion_tokens,
                   sum(
                     coalesce(prompt_tokens, 0) + coalesce(completion_tokens, 0)
                     + coalesce(aux_prompt_tokens, 0) + coalesce(aux_completion_tokens, 0)
                   ) AS total_tokens
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
