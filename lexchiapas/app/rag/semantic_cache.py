import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_ai_config
from app.models import SemanticCacheEntry
from app.rag.retriever import corpus_signature, to_vector_literal
from app.schemas.chat import ChatResponse

logger = logging.getLogger("lexchiapas.semantic_cache")


def lookup(db: Session, query_embedding: list[float]) -> ChatResponse | None:
    """Busca una respuesta ya cacheada para una pregunta semanticamente
    equivalente. Umbral MUY conservador (0.97 por defecto en ai_config.json,
    ver "_note" ahi) porque un falso positivo aqui devuelve la respuesta
    COMPLETA de una pregunta distinta -- mucho mas grave que un chunk de mas
    en retrieval normal (threshold 0.5).

    Ademas del umbral de similitud, un hit exige que la firma del corpus
    (count, max_chunk_id) de cuando se guardo la entrada coincida EXACTA con
    la firma actual -- protege contra devolver una respuesta correcta EN SU
    MOMENTO pero ya obsoleta porque la ley subyacente se re-ingirio despues
    (ver comentario en app.models.semantic_cache.SemanticCacheEntry). El
    umbral de similitud y la firma del corpus resuelven riesgos DISTINTOS:
    uno evita responder con la ley equivocada, el otro evita responder con
    una version vieja de la ley correcta.

    Solo se usa para preguntas SIN historial de conversacion (ver
    rag_pipeline.answer_question) -- una pregunta corta de seguimiento como
    "Y las multas?" depende del contexto previo de ESA conversacion en
    particular, y cachearla por similitud de embedding sola reutilizaria
    una respuesta de un contexto distinto sin darse cuenta.
    """
    ai_config = get_ai_config()["semantic_cache"]
    if not ai_config.get("enabled", True):
        return None

    count, max_id = corpus_signature(db)
    query_vector = to_vector_literal(query_embedding)
    row = db.execute(
        text(
            """
            SELECT id, response_json
            FROM semantic_cache
            WHERE created_at > now() - make_interval(days => :ttl_days)
              AND corpus_chunk_count = :corpus_count
              AND corpus_max_chunk_id = :corpus_max_id
              AND 1 - (question_embedding <=> CAST(:query_vector AS vector)) > :threshold
            ORDER BY question_embedding <=> CAST(:query_vector AS vector)
            LIMIT 1
            """
        ),
        {
            "query_vector": query_vector,
            "threshold": ai_config["similarity_threshold"],
            "ttl_days": ai_config["ttl_days"],
            "corpus_count": count,
            "corpus_max_id": max_id,
        },
    ).first()

    if row is None:
        return None

    db.execute(
        text("UPDATE semantic_cache SET hit_count = hit_count + 1, last_used_at = now() WHERE id = :id"),
        {"id": row.id},
    )
    db.commit()
    logger.info("semantic_cache HIT id=%s", row.id)
    return ChatResponse.model_validate(row.response_json)


def store(db: Session, question_text: str, query_embedding: list[float], response: ChatResponse) -> None:
    """Guarda una respuesta ya generada para reusarla en preguntas futuras
    semanticamente equivalentes. Se cachean tanto respuestas grounded=True
    como grounded=False (decision explicita, ver PLAN.md Fase 3.7): una
    pregunta legitimamente fuera del corpus tambien cuesta un
    hybrid_search+rerank completo cada vez que se repite, aunque no llegue
    a llamar al LLM principal (ver app.rag.generator.generate_answer). Solo
    se llama con preguntas SIN historial de conversacion (mismo criterio
    que lookup())."""
    count, max_id = corpus_signature(db)
    entry = SemanticCacheEntry(
        question_text=question_text,
        question_embedding=query_embedding,
        response_json=response.model_dump(mode="json"),
        corpus_chunk_count=count,
        corpus_max_chunk_id=max_id,
    )
    db.add(entry)
    db.commit()
