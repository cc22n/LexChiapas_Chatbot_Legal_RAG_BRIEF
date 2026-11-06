"""Herramientas del agente (Etapa 1 -- ver LexChiapas_Evolucion_RAG_Progresiva.md
seccion FASE 2 y PLAN.md Fase 7). Envuelven funciones YA EXISTENTES de
retrieval; no reimplementan logica de busqueda, threshold, ni reranking. El
unico codigo nuevo real aqui es get_article (lookup directo, sin embeddings)
y el uso del parametro document_filter agregado a app.rag.retriever para
search_by_law.
"""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.llm.providers import embed_text
from app.rag.agent_graph import (  # noqa: F401  (re-export: otros modulos y tests importan de aqui)
    MESES_ES,
    VERB_BY_RELATION_TYPE,
    _format_fecha,
    _relation_to_sentence,
    get_articulo_historial,
    get_articulos_historial_bulk,
    query_graph,
    relations_to_chunks,
)
from app.rag.db_session import release_connection
from app.rag.reranker import rerank
from app.rag.retriever import RetrievedChunk, fuzzy_ilike_pattern, hybrid_search, normalize_for_match

logger = logging.getLogger("lexchiapas.agent_tools")


def search_laws(
    db: Session, query_text: str, query_embedding: list[float] | None = None
) -> list[RetrievedChunk]:
    """Busqueda general: hybrid_search + rerank, exactamente como
    rag_pipeline.answer_question hoy (sin filtro de ley especifica).

    query_embedding se puede pasar precalculado (ej. el que ya se calculo
    para Capa 1 de guardrails en agent_pipeline) para no gastar una llamada
    de embeddings de mas; si no se pasa, se calcula aqui.
    """
    if query_embedding is None:
        query_embedding = embed_text(query_text)
    candidates = hybrid_search(db, query_text, query_embedding)
    release_connection(db)  # el reranker es una llamada externa
    return rerank(query_text, candidates)


def search_by_law(
    db: Session,
    law_name: str,
    query_text: str,
    query_embedding: list[float] | None = None,
) -> list[RetrievedChunk]:
    """Igual que search_laws, pero acotada a un solo documento (fuzzy_ilike_pattern
    sobre documents.nombre via el parametro document_filter de hybrid_search,
    ver app.rag.retriever) -- para cuando la pregunta ya menciona una
    ley/codigo especifico y no hace falta competir contra el corpus completo
    (evita que otra ley con lenguaje parecido desplace el articulo correcto
    del top-K). BUG REAL corregido (medido con agentic_rag activado contra
    las 24 preguntas del golden dataset): el nodo "decidir" del agente a
    veces devuelve una paraphrase del nombre de la ley (ej. "ley ambiental
    de chiapas") que un ILIKE literal no matchea contra el nombre oficial
    completo ("Ley Ambiental PARA EL ESTADO de Chiapas") -- causaba que
    busqueda_por_ley fallara a "no encontrado" para una ley que si esta en
    el corpus, mismo patron ya corregido para query_graph/get_article.
    """
    if query_embedding is None:
        query_embedding = embed_text(query_text)
    candidates = hybrid_search(db, query_text, query_embedding, document_filter=law_name)
    release_connection(db)  # el reranker es una llamada externa
    return rerank(query_text, candidates)


def get_article(db: Session, law_name: str, articulo: str) -> RetrievedChunk | None:
    """Lookup DIRECTO por documents.nombre (fuzzy_ilike_pattern, ver
    app.rag.retriever -- tolera que "decidir" devuelva una paraphrase sin
    palabras del nombre oficial, ej. "ley ambiental de chiapas" vs el
    nombre real "Ley Ambiental para el Estado de Chiapas") +
    chunks.articulo_numero (exacto) -- SIN embeddings, para cuando el
    usuario pide el contenido de un numero de articulo especifico (ej. "que
    dice el articulo 45 del codigo civil de Chiapas").

    Devuelve None si no existe esa ley en el corpus activo, o si esa ley no
    tiene ese numero de articulo -- nunca inventa ni aproxima.

    DECISION DE DISENO (gate anti-alucinacion, ver
    app.rag.agent_pipeline._node_generar para donde se usa esto): el chunk
    que devuelve esta funcion es 100% real (viene directo de la tabla
    `chunks` por clave exacta, no hay riesgo de que su CONTENIDO sea
    inventado), pero NO paso por similarity_threshold real de dense_search
    -- por eso NUNCA se marca passed_threshold=True aqui, a proposito.
    passed_threshold tiene un significado especifico y ya usado en TODO el
    pipeline ("paso el umbral real de similitud coseno de dense_search",
    ver retriever.RetrievedChunk) y reranker.rerank ordena candidatos
    priorizando ese campo -- reusarlo aqui con un criterio distinto
    ("es un chunk real de la DB", que es cierto pero no es lo que el campo
    significa en el resto del codigo) rompe esa garantia en cualquier
    otro lugar que lea passed_threshold, incluyendo el reranker si esta
    funcion alguna vez se mezcla con candidatos de hybrid_search.

    En vez de forzar este resultado a encajar en ese campo, el gate
    anti-alucinacion para la ruta de articulo especifico usa su PROPIO
    criterio explicito en agent_pipeline: "se encontro el articulo pedido
    en la DB" (chunk is not None) cuenta como fundamentado por si mismo,
    porque no hay ambiguedad semantica que evaluar -- es una cita exacta,
    no una busqueda que podria traer contenido de otro tema. La
    preocupacion real de "nunca responder con contenido no verificado"
    sigue cubierta: si el articulo no existe, se admite honestamente (no se
    inventa), y el segundo gate de grounding
    (app.rag.grounding.answer_is_grounded_in_practice) sigue aplicando
    sobre la respuesta generada para atrapar si el LLM, aun con el chunk
    correcto en mano, cito el articulo equivocado o agrego contenido que no
    esta en el chunk.

    DESAMBIGUACION (gap real documentado en LexChiapas_Plan_Futuro.md Parte
    1.D): fuzzy_ilike_pattern es un substring match, asi que puede matchear
    mas de un documento activo (ej. "codigo civil" matchea los 4 libros del
    Codigo Civil). Con el corpus actual la numeracion de articulo NUNCA
    colisiona entre esos 4 libros (son un solo codigo con numeracion
    continua, no 4 numeraciones independientes -- verificado con SQL real:
    0 numeros de articulo repetidos entre los 4 documentos), asi que un
    LIMIT 1 sin ORDER BY nunca eligio mal en la practica. Pero es fragil: si
    dos leyes con nombres parecidos algun dia SI comparten un numero de
    articulo, LIMIT 1 devolveria contenido de la ley EQUIVOCADA en silencio,
    el peor error posible para una cita legal. Ahora se traen TODAS las
    filas que matchean y, si mas de un documento distinto tiene ese mismo
    numero de articulo, se prefiere un match EXACTO de nombre (case
    insensitive) si `law_name` coincide con el nombre completo de uno de los
    documentos candidatos; si ninguno matchea exacto, es genuinamente
    ambiguo -- se registra y se devuelve None (mismo criterio "nunca
    inventa ni aproxima" que ya rige el resto de esta funcion) en vez de
    adivinar cual de los documentos es el correcto.
    """
    rows = db.execute(
        text(
            """
            SELECT c.id, d.nombre, c.articulo_numero, c.content
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.is_active = true
              AND d.nombre ILIKE :law_pattern
              AND UPPER(c.articulo_numero) = UPPER(:articulo)
            """
        ),
        {"law_pattern": fuzzy_ilike_pattern(law_name), "articulo": articulo},
    ).all()

    if not rows:
        return None

    distinct_docs = {r.nombre for r in rows}
    if len(distinct_docs) > 1:
        exact = [r for r in rows if normalize_for_match(r.nombre) == normalize_for_match(law_name)]
        if exact:
            rows = exact
        else:
            logger.warning(
                "get_article: '%s' articulo '%s' es ambiguo entre %d documentos (%s) -- "
                "sin match exacto de nombre, se rehusa a adivinar",
                law_name, articulo, len(distinct_docs), sorted(distinct_docs),
            )
            return None

    row = rows[0]
    return RetrievedChunk(
        chunk_id=row.id,
        document_nombre=row.nombre,
        articulo_numero=row.articulo_numero,
        content=row.content,
        similarity=1.0,  # no es un score semantico -- coincidencia exacta por clave
        passed_threshold=False,  # intencional, ver docstring arriba
    )


def get_article_ambiguity(db: Session, law_name: str, articulo: str) -> list[str]:
    """Companero de get_article para Fase 9.3 (coverage checker -- pedir
    aclaracion en vez de responder/rechazar, ver LexChiapas_Plan_Futuro.md).

    Pensado para llamarse SOLO cuando get_article(db, law_name, articulo)
    ya devolvio None, para distinguir DOS causas que get_article no
    diferencia en su valor de retorno: "esa ley/articulo genuinamente no
    existe en el corpus" vs. "el nombre es AMBIGUO entre 2+ leyes activas
    reales y ninguna coincide exacto" (el caso que get_article ya detecta
    internamente y registra con logger.warning, pero que hasta ahora se
    resolvia siempre como un "no encontre informacion" silencioso, sin
    decirle al usuario que el problema es ambiguedad, no ausencia).

    Devuelve la lista de nombres de documentos candidatos si es
    genuinamente ambiguo, o `[]` si no (0 candidatos reales, exactamente 1,
    o el nombre exacto ya habria resuelto cual usar -- en esos 3 casos
    get_article no devolvio None por ambiguedad, asi que no hay nada que
    aclarar). No reimplementa la logica de eleccion de get_article, corre
    la MISMA consulta por separado -- barata, y solo se llama en el caso
    raro donde get_article ya fallo."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT d.nombre
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.is_active = true
              AND d.nombre ILIKE :law_pattern
              AND UPPER(c.articulo_numero) = UPPER(:articulo)
            """
        ),
        {"law_pattern": fuzzy_ilike_pattern(law_name), "articulo": articulo},
    ).all()
    distinct_docs = sorted({r.nombre for r in rows})
    if len(distinct_docs) <= 1:
        return []
    if any(normalize_for_match(d) == normalize_for_match(law_name) for d in distinct_docs):
        return []  # el nombre exacto ya resuelve esto dentro de get_article
    return distinct_docs
