"""Consultas de las metricas del panel de administracion (/admin/metrics/*).

Cada funcion devuelve un dict listo para validarse contra el esquema de
app.schemas.admin_metrics; el SQL no cambia al mover las consultas aca.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


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
