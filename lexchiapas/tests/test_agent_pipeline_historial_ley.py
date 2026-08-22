from datetime import date

from langgraph.graph import END

from app.rag.agent_pipeline import _parse_decision, _should_retry_after_generar
from app.rag.agent_tools import (
    _format_fecha,
    _relation_to_sentence,
    relations_to_chunks,
)
from app.rag.retriever import fuzzy_ilike_pattern, normalize_for_match

# Estos tests cubren solo la logica DETERMINISTICA de la ruta nueva
# HISTORIAL_LEY (Fase 8, GraphRAG -- ver PLAN.md Fase 8 y
# app.rag.agent_pipeline docstring de modulo, invariante 6): parsing del
# output del LLM "decidir", el gate de reintento (nunca reintenta esta
# ruta), y el formateo de filas de legal_relations en RetrievedChunk
# sinteticos, todo sin llamadas a la API de NVIDIA ni a la DB. La parte que
# SI depende de la DB real (query_graph en si, preguntas reales de punta a
# punta) se probo manualmente contra la base real -- ver PLAN.md Fase 8
# para esa evidencia.


# ---------------------------------------------------------------------------
# _parse_decision
# ---------------------------------------------------------------------------


def test_parse_decision_historial_ley_with_law():
    raw = "ACCION: HISTORIAL_LEY\nLEY: codigo de atencion a la familia\nARTICULO: NINGUNA"
    assert _parse_decision(raw) == ("historial_ley", "codigo de atencion a la familia", None)


def test_parse_decision_historial_ley_case_insensitive_and_whitespace():
    raw = "  accion : Historial_Ley  \nley: Ley de Proteccion Animal\narticulo: NINGUNA"
    accion, ley, articulo = _parse_decision(raw)
    assert accion == "historial_ley"
    assert ley == "Ley de Proteccion Animal"
    assert articulo is None


def test_parse_decision_historial_ley_downgrades_to_busqueda_general_without_ley():
    # Downgrade seguro (mismo criterio que busqueda_por_ley/articulo_especifico,
    # ver docstring de _parse_decision): sin ley identificada no hay nada que
    # consultar en el grafo, cae al comportamiento por defecto ya conocido.
    raw = "ACCION: HISTORIAL_LEY\nLEY: NINGUNA\nARTICULO: NINGUNA"
    assert _parse_decision(raw) == ("busqueda_general", None, None)


def test_parse_decision_historial_ley_with_articulo_mentioned_still_needs_ley():
    # HISTORIAL_LEY no usa el campo ARTICULO para nada (query_graph busca por
    # ley completa, no por articulo puntual) pero el downgrade solo depende
    # de si hay `ley` o no -- si el LLM devuelve un articulo de todos modos,
    # no cambia el resultado.
    raw = "ACCION: HISTORIAL_LEY\nLEY: codigo penal\nARTICULO: 214"
    accion, ley, articulo = _parse_decision(raw)
    assert accion == "historial_ley"
    assert ley == "codigo penal"
    assert articulo == "214"


# ---------------------------------------------------------------------------
# _should_retry_after_generar -- historial_ley nunca reintenta
# ---------------------------------------------------------------------------


def _state(**overrides):
    base = {
        "decision": "historial_ley",
        "grounded_gate": True,
        "grounded": False,
        "intentos": 1,
        "max_intentos": 2,
    }
    base.update(overrides)
    return base


def test_historial_ley_never_retries_even_with_gate_true_and_not_grounded():
    # El escenario que SI dispara retry para busqueda_general/busqueda_por_ley
    # (grounded_gate=True, grounded=False, intentos<max) NO debe disparar
    # retry aqui -- invariante 6 del docstring de modulo: no hay ambiguedad
    # de fraseo que reformular resuelva en una consulta de grafo por nombre
    # de ley (mismo motivo que articulo_especifico).
    assert _should_retry_after_generar(_state()) == END


def test_historial_ley_never_retries_regardless_of_intentos():
    assert _should_retry_after_generar(_state(intentos=0)) == END


# ---------------------------------------------------------------------------
# _format_fecha / _relation_to_sentence / relations_to_chunks
# ---------------------------------------------------------------------------


def test_format_fecha_known_date():
    assert _format_fecha(date(2015, 6, 17)) == "17 de junio de 2015"


def test_format_fecha_none():
    assert _format_fecha(None) == "en una fecha no especificada en el marcador"


def _relation(**overrides):
    base = {
        "relation_type": "deroga",
        "from_document_id": 1,
        "from_document_nombre": "Codigo de Atencion a la Familia del Estado de Chiapas",
        "from_articulo": "93",
        "from_chunk_id": 555,
        "to_document_id": 7,
        "to_law_name_raw": "Ley de los Derechos de Ninas, Ninos y Adolescentes del Estado de Chiapas",
        "is_self_modification": False,
        "fecha": date(2015, 6, 17),
        "source_text": "(DEROGADO POR ARTICULO TERCERO TRANSITORIO DE LA LEY DE LOS DERECHOS DE NINAS, NINOS Y ADOLESCENTES DEL ESTADO DE CHIAPAS, P.O. 17 DE JUNIO DE 2015)",
        "extraction_method": "regex",
    }
    base.update(overrides)
    return base


def test_relation_to_sentence_cross_law_resolved_mentions_real_facts_only():
    sentence = _relation_to_sentence(_relation())
    assert "93" in sentence
    assert "Codigo de Atencion a la Familia del Estado de Chiapas" in sentence
    assert "fue derogado" in sentence
    assert "17 de junio de 2015" in sentence
    assert "Ley de los Derechos de Ninas, Ninos y Adolescentes del Estado de Chiapas" in sentence
    # el marcador crudo se incluye textual para permitir cita literal
    assert "DEROGADO POR ARTICULO TERCERO TRANSITORIO" in sentence


def test_relation_to_sentence_self_modification_does_not_name_another_law():
    rel = _relation(
        relation_type="reforma",
        to_document_id=1,
        to_law_name_raw="Codigo de Atencion a la Familia del Estado de Chiapas",
        is_self_modification=True,
        source_text="(REFORMADO, P.O. 23 DE SEPTIEMBRE DE 2009)",
        fecha=date(2009, 9, 23),
    )
    sentence = _relation_to_sentence(rel)
    assert "fue reformado" in sentence
    assert "23 de septiembre de 2009" in sentence
    assert "dentro de la misma ley" in sentence


def test_relation_to_sentence_cross_law_unresolved_flags_missing_document():
    rel = _relation(to_document_id=None, to_law_name_raw="LEY DE ASISTENCIA E INTEGRACION DE LAS PERSONAS ADULTAS MAYORES DEL ESTADO DE CHIAPAS")
    sentence = _relation_to_sentence(rel)
    assert "LEY DE ASISTENCIA E INTEGRACION" in sentence
    assert "no esta en el corpus ingerido actualmente" in sentence


def test_relation_to_sentence_no_articulo_no_fecha():
    rel = _relation(from_articulo=None, fecha=None)
    sentence = _relation_to_sentence(rel)
    assert "numero no identificado en el marcador" in sentence
    assert "en una fecha no especificada en el marcador" in sentence


def test_relations_to_chunks_uses_real_from_chunk_id_and_synthetic_gate_fields():
    chunks = relations_to_chunks([_relation()])
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_id == 555  # from_chunk_id real, no inventado
    assert chunk.document_nombre == "Codigo de Atencion a la Familia del Estado de Chiapas"
    assert chunk.articulo_numero == "93"
    assert chunk.similarity == 1.0
    assert chunk.passed_threshold is False  # gate propio, ver invariante 6


def test_relations_to_chunks_sentinel_for_missing_chunk_id():
    chunks = relations_to_chunks([_relation(from_chunk_id=None)])
    assert chunks[0].chunk_id == -1


def test_relations_to_chunks_empty_input_is_empty_output():
    assert relations_to_chunks([]) == []


# ---------------------------------------------------------------------------
# fuzzy_ilike_pattern (vive en app.rag.retriever, compartida por
# dense_search/sparse_search y por query_graph/get_article) -- bug real
# encontrado contra la DB real esta sesion: ver el docstring de la funcion
# para los 2 casos medidos ("ley de los derechos de ninas ninos y
# adolescentes" vs "...Ninas, Ninos..." con coma; "ley ambiental de chiapas"
# vs "Ley Ambiental PARA EL ESTADO de Chiapas" con una frase entera de mas)
# -- un ILIKE '%...%' literal nunca matcheaba ninguno de los dos.
# ---------------------------------------------------------------------------


def test_fuzzy_ilike_pattern_replaces_whitespace_with_wildcards():
    assert (
        fuzzy_ilike_pattern("ley de los derechos de ninas ninos y adolescentes")
        == "%ley%de%los%derechos%de%ninas%ninos%y%adolescentes%"
    )


def test_fuzzy_ilike_pattern_tolerates_extra_whitespace():
    assert fuzzy_ilike_pattern("  codigo   penal  ") == "%codigo%penal%"


def test_fuzzy_ilike_pattern_single_word():
    assert fuzzy_ilike_pattern("catastro") == "%catastro%"


# ---------------------------------------------------------------------------
# normalize_for_match / acentos en fuzzy_ilike_pattern (Fase 9.4, bug real
# encontrado probando el agente en vivo con agentic_rag activado): el nodo
# "decidir" del LLM escribe espanol con ortografia correcta (acentos) aunque
# se le pida copiar el nombre de la ley tal cual lo escribio el usuario --
# documents.nombre esta siempre en ASCII puro (ver CLAUDE.md), asi que un
# ILIKE literal con "Código" nunca matcheaba "Codigo" en la DB real. Antes
# de este fix, esto hacia que get_article/get_article_ambiguity/query_graph
# devolvieran "no encontrado" para leyes que SI existen en el corpus.
# ---------------------------------------------------------------------------


def test_normalize_for_match_strips_accents_and_lowercases():
    assert normalize_for_match("Código Penal para el Estado de Chiapas") == "codigo penal para el estado de chiapas"


def test_normalize_for_match_is_noop_on_plain_ascii():
    assert normalize_for_match("codigo penal") == "codigo penal"


def test_fuzzy_ilike_pattern_strips_accents_so_it_matches_ascii_db_names():
    # Mismo patron ASCII sin importar si el LLM escribio con o sin acentos --
    # el patron ILIKE resultante debe ser identico para poder matchear
    # documents.nombre (siempre ASCII) en cualquiera de los dos casos.
    assert fuzzy_ilike_pattern("Código Penal para el Estado de Chiapas") == fuzzy_ilike_pattern(
        "Codigo Penal para el Estado de Chiapas"
    )
    assert fuzzy_ilike_pattern("Código Penal para el Estado de Chiapas") == "%codigo%penal%para%el%estado%de%chiapas%"
