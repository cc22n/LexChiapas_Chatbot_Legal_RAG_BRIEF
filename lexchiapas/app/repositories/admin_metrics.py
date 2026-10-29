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
