import logging

from app.config import get_ai_config
from app.rag.reranker_router import get_relevance_scores
from app.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


def _overlap_score(query_words: set[str], chunk: RetrievedChunk) -> float:
    """Heuristica local (placeholder original de Fase 2), usada solo como
    ultimo recurso si NVIDIA y Jina (ver reranker_router.py) fallan los dos.
    """
    content_words = set(chunk.content.lower().split())
    overlap = len(query_words & content_words) / max(len(query_words), 1)
    return chunk.similarity + overlap


def rerank(query_text: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Reordena los candidatos de hybrid_search (con un reranker real via
    reranker_router.py, cayendo a una heuristica local si ambos proveedores
    externos fallan) y recorta a top-K.

    Bug real encontrado en Fase 2 con 4 leyes en el corpus, TODAVIA vigente
    con el reranker real (no era solo un problema de la heuristica vieja):
    `chunk.similarity` NO es una sola escala comparable entre chunks. Para
    los que vienen de dense_search es cosine similarity real (0-1 absoluto);
    para los que vienen SOLO de sparse_search (BM25) es el score normalizado
    al maximo POR CONSULTA (siempre hay un chunk con similarity=1.0, sin
    importar que tan irrelevante sea el mejor match de esa consulta en
    particular). Un reranker externo tiene el MISMO problema en potencia: su
    score de relevancia no sabe nada de `passed_threshold`, asi que un chunk
    de una ley totalmente distinta podria puntuar alto por el reranker y
    desplazar del top-K a chunks que SI pasaron el threshold real de
    dense_search -- produciendo `grounded: False` (falso negativo) en
    preguntas claramente dentro de dominio. Por eso se ordena SIEMPRE
    primero por `passed_threshold` (los que pasaron el gate anti-alucinacion
    real nunca quedan por debajo de los que no) y solo como criterio
    secundario por el score de relevancia (externo o heuristico) -- esto
    garantiza que `rag_pipeline.answer_question`'s
    `grounded = any(c.passed_threshold for c in top_chunks)` siga siendo
    correcto sin importar que tan bueno o malo sea el reranker de turno.
    """
    if not candidates:
        return []

    scores, provider_used = get_relevance_scores(query_text, [c.content for c in candidates])

    if scores is not None and provider_used != "none":
        reranked = [
            c for c, _ in sorted(
                zip(candidates, scores),
                key=lambda pair: (pair[0].passed_threshold, pair[1]),
                reverse=True,
            )
        ]
    else:
        logger.warning("reranker externo no disponible, usando heuristica local de solapamiento")
        query_words = set(query_text.lower().split())
        reranked = sorted(
            candidates,
            key=lambda c: (c.passed_threshold, _overlap_score(query_words, c)),
            reverse=True,
        )

    top_k = get_ai_config()["retrieval"]["top_k"]
    return reranked[:top_k]
