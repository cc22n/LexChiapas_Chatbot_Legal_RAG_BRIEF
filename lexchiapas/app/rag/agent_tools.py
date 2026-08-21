"""Herramientas del agente (Etapa 1 -- ver LexChiapas_Evolucion_RAG_Progresiva.md
seccion FASE 2 y PLAN.md Fase 7). Envuelven funciones YA EXISTENTES de
retrieval; no reimplementan logica de busqueda, threshold, ni reranking. El
unico codigo nuevo real aqui es get_article (lookup directo, sin embeddings)
y el uso del parametro document_filter agregado a app.rag.retriever para
search_by_law.
"""

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.llm.providers import embed_text
from app.rag.reranker import rerank
from app.rag.retriever import RetrievedChunk, fuzzy_ilike_pattern, hybrid_search

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
        exact = [r for r in rows if r.nombre.strip().lower() == law_name.strip().lower()]
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
    if any(d.strip().lower() == law_name.strip().lower() for d in distinct_docs):
        return []  # el nombre exacto ya resuelve esto dentro de get_article
    return distinct_docs


# ---------------------------------------------------------------------------
# query_graph (Fase 8, GraphRAG) -- ver app.models.legal_relation.LegalRelation
# y ingestion/extract_legal_relations.py para como se poblo la tabla.
# ---------------------------------------------------------------------------

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}

VERB_BY_RELATION_TYPE = {
    "reforma": "fue reformado",
    "deroga": "fue derogado",
    "adiciona": "fue adicionado",
}


def query_graph(db: Session, law_name: str, articulo: str | None = None, limit: int = 20) -> list[dict]:
    """Consulta legal_relations para una ley identificada por nombre (mismo
    campo law_name que ya usan search_by_law y get_article -- ILIKE
    substring contra documents.nombre).

    Sin `articulo` (pregunta generica sobre la historia COMPLETA de la
    ley): devuelve las relaciones donde esa ley es el ORIGEN
    (from_document_id -- a su propio articulo le paso algo:
    reforma/derogacion/adicion, ya sea auto-modificacion o por otra ley) O
    el DESTINO (to_document_id -- OTRA ley le hizo algo a esta, ej. quien
    la deroga), ordenadas por fecha descendente (mas reciente primero) y
    limitadas a `limit` filas.

    Con `articulo` (pregunta sobre UN articulo puntual, ej. "que le paso al
    articulo 93 del Codigo X" -- mismo campo que ya extrae
    agent_pipeline._parse_decision para articulo_especifico): BUG REAL
    encontrado y corregido en esta sesion -- devolver "las N relaciones mas
    recientes de TODA la ley" (el criterio de arriba) puede dejar afuera
    por completo el articulo que el usuario pidio si esa ley tiene muchas
    relaciones mas recientes que la del articulo en cuestion. Caso medido
    en vivo: "que le paso al articulo 93 del Codigo de Atencion a la
    Familia" con el Codigo de Atencion a la Familia (294 relaciones
    totales) -- la relacion real de derogacion del articulo 93 es de
    2015-06-17, pero hay 159 relaciones de esa MISMA ley con fecha
    POSTERIOR (hasta 2022), asi que con limit=20 ordenado solo por fecha
    la fila del articulo 93 nunca entraba al top-20 enviado al LLM; el
    segundo gate de grounding correctamente detecto que la respuesta no
    estaba fundamentada y se nego (no alucino), pero la respuesta debia
    poder encontrarse y no se encontraba -- un fallo de RETRIEVAL, no de
    generacion. Con `articulo` presente, el filtro cambia a EXACTO por
    from_articulo (comparando sin distinguir mayusculas/espacios, mismo
    criterio de tolerancia a sufijos "15 Bis"/"117 BIS" que
    agent_pipeline._parse_decision ya documenta) y SOLO considera el lado
    ORIGEN (from_document_id) -- un articulo puntual de ESTA ley, no
    relaciones donde esta ley aparece como actor hacia el articulo de OTRA
    ley (esas tendrian un from_articulo distinto, del otro documento).

    Si hay mas filas de las que se devuelven (solo relevante sin
    `articulo`, dado que el volumen tipico de relaciones para un solo
    articulo es bajo), se deja constancia EXPLICITA con un logger.info
    (cuantas se omitieron) -- no se mete ese conteo en el contenido de un
    chunk porque no es informacion legal real, es metadata de la consulta,
    y mezclarla arriesgaria que el LLM la cite como si fuera parte de la
    ley.

    Devuelve [] si `law_name` no matchea ningun documento activo del
    corpus, o si matchea pero no hay relaciones (para ese articulo, si se
    dio uno). El llamador no puede distinguir "ley no encontrada" de "ley
    encontrada sin historial" solo con esto, pero ambos casos deben
    producir el mismo "no encontre informacion sobre eso" honesto (ver
    gate en agent_pipeline._node_generar para la ruta historial_ley), asi
    que no hace falta distinguirlos aqui.

    DESAMBIGUACION (gap real documentado en LexChiapas_Plan_Futuro.md Parte
    1.D, mismo problema que get_article): `pattern` es substring match y
    puede matchear mas de un documento activo (ej. los 4 libros del Codigo
    Civil). Cuando se pide un `articulo` puntual, mezclar from_articulo de
    documentos DISTINTOS bajo el mismo `law_name` arriesgaria devolver la
    relacion de la ley equivocada -- si el match es ambiguo, se prefiere
    primero un nombre EXACTO (case insensitive) entre los documentos
    candidatos y se acota la consulta a ESE documento unico; si ninguno
    matchea exacto, se deja constancia con logger.warning (no se puede
    resolver aca sin adivinar) y se mantiene el comportamiento amplio
    anterior. Sin `articulo` (pregunta generica sobre TODA la ley) no se
    acota -- combinar el historial de varios documentos que comparten
    nombre parcial es un riesgo menor ahi (es una vista agregada, no una
    cita puntual), pero igual se registra con logger.info para que la
    ambiguedad sea visible en vez de silenciosa.

    Cada dict tiene: relation_type ("reforma"/"deroga"/"adiciona"),
    from_document_id, from_document_nombre, from_articulo, from_chunk_id,
    to_document_id (None si la ley referenciada no esta en el corpus
    ingerido), to_law_name_raw (nombre de texto, SIEMPRE presente),
    is_self_modification (bool -- True si el marcador no nombra a otra ley
    distinta, ver build_relation en extract_legal_relations.py), fecha
    (date o None), source_text (el marcador crudo completo, para citar
    textualmente), extraction_method ("regex" o "regex_publicada").
    """
    pattern = fuzzy_ilike_pattern(law_name)

    matched = db.execute(
        text("SELECT id, nombre FROM documents WHERE is_active = true AND nombre ILIKE :pattern"),
        {"pattern": pattern},
    ).all()
    if not matched:
        return []

    narrowed_doc_id: int | None = None
    if len(matched) > 1:
        exact = [m for m in matched if m.nombre.strip().lower() == law_name.strip().lower()]
        if articulo:
            if len(exact) == 1:
                narrowed_doc_id = exact[0].id
            else:
                logger.warning(
                    "query_graph: '%s' articulo '%s' es ambiguo entre %d documentos (%s) -- "
                    "sin match exacto de nombre, se mantiene el filtro amplio (riesgo de mezclar leyes)",
                    law_name, articulo, len(matched), sorted(m.nombre for m in matched),
                )
        else:
            logger.info(
                "query_graph: '%s' matchea %d documentos (%s) -- vista agregada, no se acota",
                law_name, len(matched), sorted(m.nombre for m in matched),
            )

    # Subquery ILIKE reusada (en vez de pasar una lista de ids como bind
    # param, que complicaria el tipado del driver) -- mismo patron que
    # dense_search/sparse_search/get_article en este mismo modulo. Si
    # narrowed_doc_id se resolvio arriba (match exacto entre varios
    # candidatos), se filtra por ESE documento puntual en vez del patron
    # amplio, para no mezclar from_articulo de otra ley con nombre parecido.
    if articulo and narrowed_doc_id is not None:
        where_clause = "lr.from_document_id = :doc_id AND UPPER(TRIM(lr.from_articulo)) = UPPER(TRIM(:articulo))"
        params_base = {"doc_id": narrowed_doc_id, "articulo": articulo}
    elif articulo:
        where_clause = (
            "lr.from_document_id IN (SELECT id FROM documents WHERE is_active = true AND nombre ILIKE :pattern) "
            "AND UPPER(TRIM(lr.from_articulo)) = UPPER(TRIM(:articulo))"
        )
        params_base = {"pattern": pattern, "articulo": articulo}
    else:
        where_clause = (
            "(lr.from_document_id IN (SELECT id FROM documents WHERE is_active = true AND nombre ILIKE :pattern) "
            "OR lr.to_document_id IN (SELECT id FROM documents WHERE is_active = true AND nombre ILIKE :pattern))"
        )
        params_base = {"pattern": pattern}

    total = db.execute(
        text(f"SELECT COUNT(*) FROM legal_relations lr WHERE {where_clause}"),
        params_base,
    ).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT lr.relation_type, lr.from_document_id, fd.nombre AS from_document_nombre,
                   lr.from_articulo, lr.from_chunk_id, lr.to_document_id, lr.to_law_name_raw,
                   lr.fecha, lr.source_text, lr.extraction_method
            FROM legal_relations lr
            JOIN documents fd ON fd.id = lr.from_document_id
            WHERE {where_clause}
            ORDER BY lr.fecha DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {**params_base, "limit": limit},
    ).all()

    if total > len(rows):
        logger.info(
            "query_graph: ley=%r articulo=%r tiene %d relaciones totales, se devuelven %d (omitidas %d por limite=%d)",
            law_name, articulo, total, len(rows), total - len(rows), limit,
        )

    return [
        {
            "relation_type": row.relation_type,
            "from_document_id": row.from_document_id,
            "from_document_nombre": row.from_document_nombre,
            "from_articulo": row.from_articulo,
            "from_chunk_id": row.from_chunk_id,
            "to_document_id": row.to_document_id,
            "to_law_name_raw": row.to_law_name_raw,
            "is_self_modification": row.to_document_id == row.from_document_id,
            "fecha": row.fecha,
            "source_text": row.source_text,
            "extraction_method": row.extraction_method,
        }
        for row in rows
    ]


def _format_fecha(fecha: date | None) -> str:
    if fecha is None:
        return "en una fecha no especificada en el marcador"
    mes = MESES_ES.get(fecha.month, str(fecha.month))
    return f"{fecha.day} de {mes} de {fecha.year}"


def _relation_to_sentence(rel: dict) -> str:
    """Construye UNA oracion en espanol a partir de una fila REAL de
    legal_relations (via query_graph) -- nunca agrega informacion que no
    este en la fila. Incluye el marcador original textual al final para que
    el LLM generador pueda citarlo literalmente en vez de parafrasear un
    hecho legal delicado (fecha exacta / quien deroga / que articulo)."""
    verb = VERB_BY_RELATION_TYPE.get(rel["relation_type"], "tuvo un cambio registrado")
    fecha_display = _format_fecha(rel["fecha"])
    articulo = rel["from_articulo"]
    articulo_phrase = (
        f"El articulo {articulo}" if articulo
        else "Un articulo (numero no identificado en el marcador)"
    )

    if rel["is_self_modification"]:
        actor_phrase = (
            "mediante una reforma registrada dentro de la misma ley "
            "(el marcador no nombra a otra ley distinta)"
        )
    else:
        actor_phrase = f"por {rel['to_law_name_raw']}"
        if rel["to_document_id"] is None:
            actor_phrase += (
                " (esa ley no esta en el corpus ingerido actualmente, "
                "no se puede mostrar su contenido)"
            )

    return (
        f"{articulo_phrase} de {rel['from_document_nombre']} {verb} el {fecha_display}, "
        f"{actor_phrase}. Marcador original del Periodico Oficial: \"{rel['source_text']}\"."
    )


def relations_to_chunks(relations: list[dict]) -> list[RetrievedChunk]:
    """Convierte el output de query_graph en RetrievedChunk sinteticos, mismo
    patron que get_article arriba (similarity=1.0, passed_threshold=False a
    proposito -- ver docstring de get_article para el razonamiento completo:
    no es un score de similitud semantica real, y el gate anti-alucinacion
    de esta ruta (ver app.rag.agent_pipeline._node_generar, rama
    historial_ley) usa su propio criterio explicito -- "se encontraron
    relaciones reales" (len(chunks) > 0) -- nunca passed_threshold.

    chunk_id usa from_chunk_id (el chunk REAL de donde salio el marcador,
    ver legal_relations.from_chunk_id) en vez de un id sintetico inventado
    -- es una referencia real y trazable a la tabla chunks. Si por algun
    motivo from_chunk_id fuera NULL (no deberia pasar con los datos
    actuales -- extract_legal_relations.py siempre lo puebla desde el chunk
    que esta iterando), se usa -1 como centinela explicito para no romper
    el tipo `int` de RetrievedChunk.chunk_id.
    """
    return [
        RetrievedChunk(
            chunk_id=rel["from_chunk_id"] if rel["from_chunk_id"] is not None else -1,
            document_nombre=rel["from_document_nombre"],
            articulo_numero=rel["from_articulo"],
            content=_relation_to_sentence(rel),
            similarity=1.0,
            passed_threshold=False,
        )
        for rel in relations
    ]
