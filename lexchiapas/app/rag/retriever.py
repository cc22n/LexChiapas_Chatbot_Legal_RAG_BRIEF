import heapq
import unicodedata
from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_ai_config
from app.models import Chunk, Document


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_nombre: str
    articulo_numero: str | None
    content: str
    similarity: float
    passed_threshold: bool = False
    """True solo si vino de dense_search y supero similarity_threshold. BM25
    (sparse_search) normaliza su mejor resultado a 1.0 sin importar que tan
    irrelevante sea, y no tiene un umbral absoluto comparable al de dense —
    por eso un chunk que SOLO aparece por sparse nunca puede por si solo
    justificar una respuesta grounded (ver rag_pipeline.answer_question)."""


def normalize_for_match(text_value: str) -> str:
    """Quita acentos/diacriticos (NFKD + descarta marcas combinantes) y baja
    a minusculas -- usado para comparar contra `documents.nombre`, que en
    este corpus SIEMPRE esta en ASCII puro (ver CLAUDE.md, convencion de
    ingesta). Compartido por fuzzy_ilike_pattern (para construir el patron
    ILIKE) y por las comparaciones de nombre EXACTO en agent_tools.py
    (get_article/get_article_ambiguity/query_graph).

    BUG REAL (Fase 9.4, prueba en vivo del agente con agentic_rag activado
    en produccion): el nodo "decidir" (LLM) escribe espanol con ortografia
    correcta ("Codigo" -> "Codigo" con acento en la o, "Código") incluso
    cuando el prompt le pide copiar el nombre de la ley TAL CUAL lo escribio
    el usuario -- un ILIKE literal contra documents.nombre (ASCII, sin
    acentos) fallaba con 0 filas para CUALQUIER nombre de ley que el LLM
    acentuara, no solo el caso ambiguo que se estaba arreglando. Sin esto,
    pedirle al LLM el nombre completo para desambiguar (ver Ejemplo 6 de
    DECIDE_SYSTEM_PROMPT en agent_pipeline.py) empeoraba las cosas en vez de
    arreglarlas: antes del nombre completo al menos se obtenia la lista de
    candidatos ambiguos; con el nombre completo pero acentuado, no se
    encontraba nada en absoluto."""
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text_value) if not unicodedata.combining(c)
    )
    return stripped.strip().lower()


def fuzzy_ilike_pattern(name: str) -> str:
    """Patron ILIKE tolerante a CUALQUIER texto (puntuacion, palabras de mas)
    entre los tokens (separados por espacio) de `name` -- usado por
    document_filter en dense_search/sparse_search de este modulo y por
    app.rag.agent_tools.query_graph/get_article.

    BUG REAL encontrado (Fase 7 agente, medido contra las 24 preguntas del
    golden dataset con agentic_rag activado): el nodo "decidir" devuelve
    nombres de ley PARAFRASEADOS a partir de como los escribio el usuario,
    no siempre el nombre oficial completo -- ej. la pregunta real
    "...la Ley Ambiental de Chiapas?" hizo que "decidir" devolviera
    law_name="ley ambiental de chiapas", pero el nombre real en
    documents.nombre es "Ley Ambiental para el Estado de Chiapas" (con
    "para el Estado" en medio). Un ILIKE '%ley ambiental de chiapas%'
    literal NUNCA matchea eso -- confirmado con una query directa (0 filas)
    antes de este fix -- asi que search_by_law/get_article fallaban a
    "no encontrado" para una ley que SI existe, indistinguible de que la ley
    de verdad no estuviera en el corpus (fallo de RETRIEVAL, no de datos).
    Mismo patron ya corregido antes para query_graph (Fase 8, caso real:
    "ninas ninos" vs el nombre real "Ninas, Ninos" con coma) -- ahi el gap
    era solo puntuacion; aca el gap es una FRASE completa faltante ("para el
    Estado"), y este mismo patron lo resuelve igual porque el comodin '%'
    de SQL matchea cualquier cantidad de caracteres entre los tokens
    buscados, no solo un caracter de puntuacion -- confirmado con SQL real:
    'Ley Ambiental para el Estado de Chiapas' ILIKE '%ley%ambiental%de%chiapas%'
    -> 1 fila.

    Centralizado aca (antes vivia duplicado como funcion privada en
    agent_tools.py) para que dense_search/sparse_search (usadas por
    search_by_law, la ruta busqueda_por_ley del agente) y query_graph/
    get_article compartan el mismo criterio -- son el mismo problema real,
    no dos bugs distintos."""
    tokens = [_escape_ilike_wildcards(t) for t in normalize_for_match(name).split() if t]
    return "%" + "%".join(tokens) + "%"


def _escape_ilike_wildcards(token: str) -> str:
    """Escapa los comodines propios de ILIKE (%, _) y el caracter de escape
    (\\) dentro de un token ANTES de que fuzzy_ilike_pattern lo una con sus
    propios '%' de separador -- sin esto, un law_name con '%' o '_' (viene
    del nodo "decidir" del LLM en la ruta agentica, o de texto libre del
    usuario en /api/legal-relations?law=) ensancha el patron de forma no
    intencionada (ej. "_" matchea cualquier caracter) y puede debilitar la
    desambiguacion anti-alucinacion que get_article/query_graph implementan
    con tanto cuidado. No es SQL injection (el patron completo sigue
    viajando como bind param, nunca concatenado al texto de la query), es
    escapado semantico del propio ILIKE."""
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _fuzzy_contains(haystack: str, needle: str) -> bool:
    """Equivalente Python (sin SQL) de fuzzy_ilike_pattern, para el filtro
    post-scoring de sparse_search (BM25 no corre en SQL, el filtro de
    document_filter se aplica en memoria sobre los resultados ya rankeados)."""
    import re

    tokens = [re.escape(t) for t in needle.strip().split() if t]
    if not tokens:
        return True
    return re.search(".*".join(tokens), haystack, re.IGNORECASE) is not None


def to_vector_literal(embedding: list[float]) -> str:
    """psycopg manda una lista de Python como double precision[], y pgvector
    no tiene el operador <=> para ese tipo contra vector. Hay que mandarlo
    como el literal de texto de pgvector ("[0.1,0.2,...]") y castear ::vector
    en el SQL.
    """
    return "[" + ",".join(repr(x) for x in embedding) + "]"


def dense_search(
    db: Session,
    query_embedding: list[float],
    k: int,
    threshold: float,
    document_filter: str | None = None,
) -> list[RetrievedChunk]:
    """Busqueda por similitud coseno en pgvector, descarta por debajo del threshold.

    El threshold se aplica ANTES de devolver candidatos: es el gate
    anti-alucinacion, nunca debe omitirse.

    document_filter (agente, Etapa 1, ver app.rag.agent_tools.search_by_law):
    substring case-insensitive opcional contra documents.nombre. Por default
    None -- no filtra nada, mismo comportamiento de siempre para todas las
    llamadas existentes (hybrid_search desde rag_pipeline.answer_question).
    Se arma el patron ILIKE aqui (no se pide al llamador que mande '%...%')
    para que agent_tools pueda pasar el nombre de ley tal cual.
    """
    query_vector = to_vector_literal(query_embedding)
    document_pattern = fuzzy_ilike_pattern(document_filter) if document_filter else None
    rows = db.execute(
        text(
            """
            SELECT c.id, d.nombre, c.articulo_numero, c.content,
                   1 - (c.embedding <=> CAST(:query_vector AS vector)) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.is_active = true
              AND 1 - (c.embedding <=> CAST(:query_vector AS vector)) > :threshold
              AND (CAST(:document_pattern AS text) IS NULL OR d.nombre ILIKE :document_pattern)
            ORDER BY c.embedding <=> CAST(:query_vector AS vector)
            LIMIT :k
            """
        ),
        {"query_vector": query_vector, "threshold": threshold, "k": k, "document_pattern": document_pattern},
    ).all()

    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_nombre=row.nombre,
            articulo_numero=row.articulo_numero,
            content=row.content,
            similarity=float(row.similarity),
            passed_threshold=True,  # ya filtrado por WHERE ... > :threshold en el SQL
        )
        for row in rows
    ]


# Cache en memoria del indice BM25 -- ver _get_bm25_index() para el
# invariante que lo mantiene correcto (no confiar en TTL, invalidar por
# firma real del corpus).
_bm25_cache: dict[str, object] = {"signature": None, "bm25": None, "rows": None}


def corpus_signature(db: Session) -> tuple[int, int]:
    """Firma barata (COUNT + MAX id de chunks activos) para detectar si el
    corpus cambio desde la ultima vez que se construyo el indice BM25.

    Bug real de performance encontrado en Fase 3.6: con el corpus creciendo
    de 4 leyes a 17 (7746 chunks), sparse_search reconstruia BM25Okapi desde
    cero en CADA pregunta -- ~5 segundos solo en eso, medido en vivo, antes
    de sumar dense_search/reranking/generacion. La ingesta de una ley nueva
    (o desactivar una, como se hizo con el Codigo de la Hacienda Publica
    duplicado) es un evento raro comparado con las preguntas de chat, que
    son muy frecuentes -- tiene sentido cachear el indice y solo
    reconstruirlo cuando el corpus de verdad cambio, no en cada consulta.
    Esta query (COUNT+MAX indexados) es ordenes de magnitud mas barata que
    reconstruir BM25, y funciona incluso si el corpus cambio desde OTRO
    proceso (ej. un script de ingesta `load_*.py` corriendo aparte) porque
    siempre se compara contra el estado real de la DB, no contra memoria.
    """
    count, max_id = db.execute(
        select(func.count(Chunk.id), func.coalesce(func.max(Chunk.id), 0))
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.is_active.is_(True))
    ).one()
    return (count, max_id)


def _get_bm25_index(db: Session) -> tuple[BM25Okapi | None, list]:
    """rows se cachea como tuplas de datos planos (chunk_id, nombre,
    articulo_numero, content), NUNCA como instancias ORM `Chunk`.

    BUG REAL encontrado (agentic_rag activado, 2 requests web reales
    consecutivas sobre el mismo proceso uvicorn): antes, `rows` cacheaba
    `db.execute(...).all()` directo, que son instancias ORM atadas a la
    Session de la request que las cargo (FastAPI `Depends(get_db)` cierra
    esa Session al terminar la request). La request siguiente, con
    corpus_signature igual (cache hit), reusaba esos objetos ya
    "detached" -- acceder a chunk.id/chunk.content en sparse_search
    disparaba sqlalchemy.orm.exc.DetachedInstanceError. El cache en si es
    un dict a nivel de modulo (sobrevive entre requests/Sessions a
    proposito, ver docstring de corpus_signature), asi que su contenido no
    puede depender de ninguna Session en particular -- de ahi extraer a
    tuplas planas aqui mismo, dentro de la Session que SI es valida en
    este momento, antes de cachear."""
    signature = corpus_signature(db)
    if _bm25_cache["signature"] == signature:
        return _bm25_cache["bm25"], _bm25_cache["rows"]

    stmt = (
        select(Chunk, Document.nombre)
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.is_active.is_(True))
    )
    rows = [
        (chunk.id, nombre, chunk.articulo_numero, chunk.content)
        for chunk, nombre in db.execute(stmt).all()
    ]
    bm25 = BM25Okapi([content.lower().split() for _, _, _, content in rows]) if rows else None

    _bm25_cache["signature"] = signature
    _bm25_cache["bm25"] = bm25
    _bm25_cache["rows"] = rows
    return bm25, rows


def sparse_search(
    db: Session, query_text: str, k: int, document_filter: str | None = None
) -> list[RetrievedChunk]:
    """Busqueda BM25 por keywords legales exactos sobre los chunks activos.

    document_filter (ver dense_search arriba): substring case-insensitive
    opcional contra el nombre del documento. El indice BM25 en si NUNCA se
    reconstruye filtrado (se sigue calculando IDF sobre el corpus activo
    completo, cacheado por _get_bm25_index) -- el filtro se aplica DESPUES de
    puntuar, sobre los resultados ya rankeados, igual que cualquier otro
    filtro de metadata post-scoring. Por default None, sin cambios para las
    llamadas existentes.
    """
    bm25, rows = _get_bm25_index(db)
    if not rows or bm25 is None:
        return []

    scores = bm25.get_scores(query_text.lower().split())
    pairs = list(zip(rows, scores))

    if document_filter:
        pairs = [pair for pair in pairs if _fuzzy_contains(pair[0][1], document_filter)]

    # heapq.nlargest es equivalente a sorted(pairs, key=..., reverse=True)[:k]
    # (mismo desempate, mismo resultado -- documentado por la stdlib) pero
    # O(n log k) en vez de O(n log n): no hace falta ordenar TODO el corpus
    # activo (miles de chunks) para quedarse solo con los primeros k
    # (auditoria de calidad de codigo, 2026-08-06).
    scored = heapq.nlargest(k, pairs, key=lambda pair: pair[1])
    max_score = max((s for _, s in scored), default=1.0) or 1.0

    return [
        RetrievedChunk(
            chunk_id=chunk_id,
            document_nombre=nombre,
            articulo_numero=articulo_numero,
            content=content,
            similarity=score / max_score,
        )
        for (chunk_id, nombre, articulo_numero, content), score in scored
        if score > 0
    ]


def hybrid_search(
    db: Session, query_text: str, query_embedding: list[float], document_filter: str | None = None
) -> list[RetrievedChunk]:
    """Combina dense + sparse segun los pesos de ai_config.json y aplica threshold.

    document_filter: ver dense_search/sparse_search arriba (agente, Etapa 1).
    Por default None -- sin cambios para rag_pipeline.answer_question.
    """
    ai_config = get_ai_config()
    retrieval_config = ai_config["retrieval"]
    # Multiplicador de k (Fase 3.7, investigacion de causas raiz): con *3
    # (k=15 con top_k=5) se verifico un caso real donde el chunk correcto
    # (Codigo de Atencion a la Familia Art.2, "adulto mayor") pasaba el
    # threshold real de dense_search con similitud 0.5522 pero caia en la
    # posicion 16/30 -- un lugar FUERA del pool de candidatos, asi que nunca
    # llegaba siquiera a competir en el reranker. *4 (k=20) le da margen sin
    # disparar el costo de reranking tanto como *5.
    k = retrieval_config["top_k"] * 4  # traer mas candidatos, el reranker recorta a top_k
    threshold = retrieval_config["similarity_threshold"]
    dense_weight = retrieval_config["dense_weight"]
    sparse_weight = retrieval_config["sparse_weight"]

    dense_results = dense_search(db, query_embedding, k, threshold, document_filter=document_filter)
    sparse_results = sparse_search(db, query_text, k, document_filter=document_filter)

    merged: dict[int, RetrievedChunk] = {}
    scores: dict[int, float] = {}

    for r in dense_results:
        merged[r.chunk_id] = r
        scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + dense_weight * r.similarity

    for r in sparse_results:
        merged.setdefault(r.chunk_id, r)
        scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + sparse_weight * r.similarity

    ordered_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [merged[cid] for cid in ordered_ids]
