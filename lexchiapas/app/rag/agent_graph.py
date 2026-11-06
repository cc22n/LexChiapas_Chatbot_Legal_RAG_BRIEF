"""Navegacion del grafo de reformas legales (Fase 8, GraphRAG). Separado de
agent_tools.py sin cambiar logica; agent_tools re-exporta estos nombres
(agent_pipeline, rag_pipeline, api/public y los tests los importan de ahi)."""

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.rag.retriever import RetrievedChunk, fuzzy_ilike_pattern, normalize_for_match

logger = logging.getLogger("lexchiapas.agent_tools")


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
        exact = [m for m in matched if normalize_for_match(m.nombre) == normalize_for_match(law_name)]
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


def get_articulo_historial(db: Session, document_nombre: str, articulo_numero: str | None) -> list[str]:
    """Companero de query_graph para Fase 9.4 (historial de reformas visible
    directamente en la respuesta del chat, sin que el usuario tenga que ir a
    /explorar por separado).

    Se llama con el nombre LITERAL del documento tal como quedo en el chunk
    citado (c.document_nombre, nunca una entrada libre de usuario) -- al ser
    el nombre exacto, query_graph lo resuelve sin ambiguedad aunque ese
    nombre matchee mas de un documento por ILIKE (ver narrowed_doc_id en
    query_graph). Devuelve [] si no hay numero de articulo que acotar (ej.
    chunks de encabezado/glosario sin articulo_numero) o si el articulo
    simplemente nunca tuvo una relacion registrada -- el caso normal, la
    gran mayoria de articulos nunca fueron reformados.
    """
    if not articulo_numero:
        return []
    relations = query_graph(db, document_nombre, articulo=articulo_numero, limit=10)
    return [_relation_to_sentence(rel) for rel in relations]


def get_articulos_historial_bulk(
    db: Session, pairs: list[tuple[str, str | None]]
) -> dict[tuple[str, str], list[str]]:
    """Version en lote de get_articulo_historial: resuelve el historial de
    TODOS los (document_nombre, articulo_numero) de una respuesta con 2
    queries en total, en vez de 3 por chunk (N+1, hallazgo ALT-04 de la
    auditoria 2026-10-21).

    Mantiene la semantica de query_graph(articulo=...): el nombre se resuelve
    por ILIKE contra documentos activos; si matchea mas de uno y exactamente
    uno coincide por nombre normalizado, se acota a ese documento (si no, se
    mantiene el filtro amplio y se deja logger.warning). Las relaciones son
    las del lado ORIGEN, comparando from_articulo sin distinguir mayusculas/
    espacios, mas recientes primero, maximo 10 por articulo.

    Devuelve {(document_nombre, articulo_numero): [oraciones]} solo para
    pares con articulo; los pares sin articulo o sin relaciones quedan
    ausentes (el llamador usa .get(par, [])).
    """
    wanted = sorted({(nombre, articulo) for nombre, articulo in pairs if articulo})
    if not wanted:
        return {}

    nombres = sorted({nombre for nombre, _ in wanted})
    matched_rows = db.execute(
        text(
            """
            SELECT p.idx, d.id, d.nombre
            FROM unnest(CAST(:patterns AS text[])) WITH ORDINALITY AS p(pat, idx)
            JOIN documents d ON d.is_active = true AND d.nombre ILIKE p.pat
            """
        ),
        {"patterns": [fuzzy_ilike_pattern(nombre) for nombre in nombres]},
    ).all()

    matched_by_nombre: dict[str, list[tuple[int, str]]] = {nombre: [] for nombre in nombres}
    for row in matched_rows:
        matched_by_nombre[nombres[row.idx - 1]].append((row.id, row.nombre))

    doc_ids_by_nombre: dict[str, set[int]] = {}
    for nombre, matched in matched_by_nombre.items():
        doc_ids = {doc_id for doc_id, _ in matched}
        if len(matched) > 1:
            exact = [doc_id for doc_id, doc_nombre in matched if normalize_for_match(doc_nombre) == normalize_for_match(nombre)]
            if len(exact) == 1:
                doc_ids = {exact[0]}
            else:
                logger.warning(
                    "get_articulos_historial_bulk: '%s' es ambiguo entre %d documentos (%s) -- "
                    "sin match exacto de nombre, se mantiene el filtro amplio",
                    nombre, len(matched), sorted(doc_nombre for _, doc_nombre in matched),
                )
        doc_ids_by_nombre[nombre] = doc_ids

    all_doc_ids = sorted(set().union(*doc_ids_by_nombre.values()))
    if not all_doc_ids:
        return {}

    rows = db.execute(
        text(
            """
            SELECT lr.relation_type, lr.from_document_id, fd.nombre AS from_document_nombre,
                   lr.from_articulo, lr.from_chunk_id, lr.to_document_id, lr.to_law_name_raw,
                   lr.fecha, lr.source_text, lr.extraction_method
            FROM legal_relations lr
            JOIN documents fd ON fd.id = lr.from_document_id
            WHERE lr.from_document_id = ANY(CAST(:doc_ids AS int[]))
              AND UPPER(TRIM(lr.from_articulo)) = ANY(CAST(:articulos AS text[]))
            """
        ),
        {
            "doc_ids": all_doc_ids,
            "articulos": sorted({articulo.strip().upper() for _, articulo in wanted}),
        },
    ).all()

    result: dict[tuple[str, str], list[str]] = {}
    for nombre, articulo in wanted:
        articulo_key = articulo.strip().upper()
        doc_ids = doc_ids_by_nombre[nombre]
        matching = [
            row for row in rows
            if row.from_document_id in doc_ids and (row.from_articulo or "").strip().upper() == articulo_key
        ]
        matching.sort(key=lambda row: row.fecha or date.min, reverse=True)
        sentences = [
            _relation_to_sentence(
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
            )
            for row in matching[:10]
        ]
        if sentences:
            result[(nombre, articulo)] = sentences
    return result
