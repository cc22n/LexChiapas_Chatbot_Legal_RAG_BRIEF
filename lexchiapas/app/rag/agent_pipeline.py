"""Ruta ALTERNATIVA de RAG agentico sobre LangGraph (Etapa 1 + Etapa 2 --
ver LexChiapas_Evolucion_RAG_Progresiva.md seccion FASE 2 y PLAN.md Fase 7).

NO reemplaza app.rag.rag_pipeline.answer_question (pipeline lineal, sigue
siendo la ruta por default). Esta funcion tiene la MISMA firma para poder
intercambiarlas facil; el punto de entrada real (app.bots.conversation_store.
handle_turn) elige cual usar segun ai_config.json "agentic_rag.enabled"
(default false hasta medir).

Etapa 1 = agente basico SIN loop de auto-evaluacion: un solo intento de
busqueda por pregunta. El grafo tiene 3 nodos sin ciclos:

    START -> decidir -> buscar -> generar -> END

- "decidir": un LLM barato (generate_with_fallback, mismo patron de
  app.rag.query_rewriting/app.rag.grounding) lee la pregunta y elige UNA de
  5 acciones: NINGUNA (no hace falta buscar), BUSQUEDA_GENERAL (hybrid
  search normal), BUSQUEDA_POR_LEY (la pregunta menciona una ley
  especifica), ARTICULO_ESPECIFICO (la pregunta pide un numero de articulo
  exacto), HISTORIAL_LEY (Fase 8, GraphRAG -- la pregunta es sobre la
  HISTORIA de una ley/articulo: reformas, derogaciones, adiciones, "que le
  paso a X ley", en vez de su contenido vigente actual). Si la llamada
  falla o el output no se puede parsear, el default seguro es
  BUSQUEDA_GENERAL -- exactamente el comportamiento del pipeline lineal
  hoy, nunca un default mas arriesgado.
- "buscar": ejecuta la herramienta de app.rag.agent_tools correspondiente a
  la decision.
- "generar": llama a app.rag.generator.generate_answer TAL CUAL ya existe
  (sin reescribirla), con los chunks encontrados (o [] si no se encontro
  nada bueno).

Etapa 2 (self-reflection, NUEVO) agrega UN reintento acotado cuando el
segundo gate de grounding degrada `grounded=True` a `False` despues de
generar con chunks que SI pasaron el threshold real:

    START -> decidir -> buscar -> generar -> (condicional) -> reformular -> buscar -> generar -> END
                                       |                                                    ^
                                       +----------------------------- (si no aplica retry) -+--> END

Bandera config-driven `ai_config.json` "agentic_rag.self_reflection.enabled"
(default false hasta medir, ver PLAN.md Fase 7 Etapa 2 para la medicion real
que justifica el valor) + "max_intentos" (tope duro, ver
`_should_retry_after_generar` abajo). Ver docstring de `_node_reformular` y
`_should_retry_after_generar` para el diseno completo del reintento
(que cambia entre intentos, cuando se activa, y por que se descarto la
alternativa de cambiar de ruta de busqueda en vez de reformular).

INVARIANTES QUE ESTE MODULO NO PUEDE ROMPER (ver instrucciones de la
tarea, leelas dos veces si vas a tocar este archivo):

1. Capa 1 de guardrails (app.rag.guardrails.classify_intent) corre FUERA del
   grafo/control del agente -- el agente nunca decide si algo esta fuera de
   dominio, eso ya esta resuelto antes de invocar el grafo. Se evalua SOLO en
   el primer turno de la conversacion (sin conversation_history); un
   seguimiento dentro de una conversacion ya establecida como legal no se
   re-evalua aislado -- ver rag_pipeline.answer_question para el bug real
   que motivo este cambio (mismo criterio en ambos pipelines).
2. El gate anti-alucinacion real para la ruta de busqueda semantica
   (BUSQUEDA_GENERAL / BUSQUEDA_POR_LEY) sigue siendo EXACTAMENTE
   `any(c.passed_threshold for c in chunks)` -- el mismo campo, calculado
   por el mismo dense_search, con el mismo threshold de ai_config.json. El
   agente no puede "decidir" saltarse esto ni inventar que un chunk paso el
   threshold.
3. La ruta de ARTICULO_ESPECIFICO (ver app.rag.agent_tools.get_article para
   la decision de diseno completa) usa su PROPIO gate explicito --
   "se encontro el articulo pedido en la DB" -- documentado ahi y en
   _node_generar abajo, nunca reusa passed_threshold=True para un chunk que
   no paso por similitud semantica real. El loop de self-reflection de
   Etapa 2 NUNCA reintenta esta ruta (ver _should_retry_after_generar): no
   hay ambiguedad de fraseo que resolver reformulando -- el articulo existe
   en la DB con ese numero exacto, o no existe.
4. El segundo gate de grounding (app.rag.grounding.
   answer_is_grounded_in_practice) se aplica SIEMPRE despues de generar,
   sin importar que ruta tomo el agente -- solo puede degradar
   grounded=True a False, nunca al reves. Etapa 2 NUNCA relaja este gate
   para forzar un "exito" -- si el reintento tambien degrada a False, se
   agotan los intentos y se admite honestamente (mismo texto NO_ENCONTRADO
   que ya usa app.rag.generator cuando no hay chunks, o la respuesta ya
   generada -- que tipicamente ya se niega en su propio texto, ver
   app.rag.grounding -- con el flag grounded=False).
5. NUEVO (Etapa 2): tope duro de `max_intentos` (default 2, ver
   ai_config.json) -- nunca mas de 1 reintento total, sin excepcion. Ver
   `_should_retry_after_generar`.
6. NUEVO (Fase 8, GraphRAG): la ruta HISTORIAL_LEY (ver
   app.rag.agent_tools.query_graph/relations_to_chunks) tiene su PROPIO
   gate explicito, mismo patron que invariante 3: "se encontraron
   relaciones reales en legal_relations para esa ley" (len(chunks) > 0),
   nunca passed_threshold=True -- las filas vienen de un lookup exacto por
   nombre de documento, no de similitud semantica. Tampoco reintenta en
   Etapa 2 (ver _should_retry_after_generar), mismo motivo que
   ARTICULO_ESPECIFICO: no hay ambiguedad de fraseo que una reformulacion
   de texto de busqueda pueda resolver en una consulta de grafo por nombre
   de ley.
"""

import json
import logging
import re
import time
from typing import TypedDict

from sqlalchemy.orm import Session

from langgraph.graph import END, START, StateGraph

from app.config import get_ai_config
from app.llm.providers import embed_text
from app.llm.router import AllModelsFailedError, generate_with_fallback
from app.rag.agent_tools import (
    get_article,
    get_article_ambiguity,
    get_articulo_historial,
    query_graph,
    relations_to_chunks,
    search_by_law,
    search_laws,
)
from app.rag.generator import generate_answer
from app.rag.grounding import answer_is_grounded_in_practice
from app.rag.guardrails import OUT_OF_SCOPE_MESSAGE, classify_intent, detect_smalltalk_response
from app.rag.legal_synonyms import expand_legal_synonyms
from app.rag.query_rewriting import CLARIFICATION_QUESTION_MARKER, rewrite_query
from app.rag.retriever import RetrievedChunk
from app.rag.semantic_cache import lookup as cache_lookup, store as cache_store
from app.rag.vigencia import is_articulo_derogado
from app.schemas.chat import AgentTrace, ChatResponse, RetrievedChunk as RetrievedChunkSchema

logger = logging.getLogger("lexchiapas.agent_pipeline")


# ---------------------------------------------------------------------------
# Nodo "decidir"
# ---------------------------------------------------------------------------

# Migrado a JSON mode (2026-08-06, auditoria de integracion LLM -- ver
# LexChiapas_Plan_Futuro.md Parte C.1 para el experimento real que confirmo
# response_format={"type":"json_object"} viable en 4/5 proveedores del
# fallback_order: minimax-m3, glm-5.2, gpt-4o-mini, grok-4.20 aceptaron el
# parametro y devolvieron JSON valido de forma confiable; deepseek-v4-pro
# dio timeout en el experimento, INCONCLUSO por infra, no por
# incompatibilidad real -- si falla con este parametro, generate_with_fallback
# ya lo trata como cualquier otro fallo de proveedor y pasa al siguiente). El
# parser de texto plano (_parse_decision) se mantiene intacto como red de
# seguridad para el proveedor que ignore response_format -- ver
# _parse_decision_json/_parse_decision abajo.
DECIDE_SYSTEM_PROMPT = (
    "Analizas una pregunta de un usuario sobre leyes y reglamentos de "
    "Chiapas, Mexico, para decidir COMO buscar la respuesta. Responde "
    "UNICAMENTE con un objeto JSON, sin texto adicional antes ni despues, "
    "con EXACTAMENTE estas 3 claves:\n"
    '{"accion": "<NINGUNA|BUSQUEDA_GENERAL|BUSQUEDA_POR_LEY|ARTICULO_ESPECIFICO|HISTORIAL_LEY>", '
    '"ley": <nombre de la ley o codigo mencionado explicitamente, o null>, '
    '"articulo": <numero de articulo mencionado explicitamente, o null>}\n\n'
    "Para 'ley': si el usuario escribio un nombre COMPLETO u oficial (incluye "
    "frases como 'de Procedimientos', 'para el Estado de Chiapas', numero de "
    "Libro, etc.), copialo TAL CUAL lo escribio, sin acortarlo -- varias leyes "
    "de Chiapas comparten las mismas palabras clave (ej. 'Codigo Penal' vs "
    "'Codigo de Procedimientos Penales'; los distintos Libros del 'Codigo "
    "Civil') y acortar el nombre le impide al sistema distinguir cual de "
    "ellas es. Usa una forma corta/generica (ej. 'codigo penal') SOLO cuando "
    "el usuario mismo la uso de forma corta.\n\n"
    "Usa ARTICULO_ESPECIFICO SOLO si la pregunta pide el contenido VIGENTE de "
    "un numero de articulo concreto de una ley identificable (ej. 'que dice "
    "el articulo 45 del codigo civil de Chiapas'). Usa HISTORIAL_LEY si la "
    "pregunta es sobre la HISTORIA de una ley o articulo -- sus reformas, "
    "derogaciones, adiciones, o que le paso a traves del tiempo (ej. 'que "
    "reformas ha tenido el codigo civil de Chiapas', 'que le paso a la ley "
    "de proteccion animal', 'cuando se reformo el articulo 214 del codigo "
    "penal') -- en vez de su contenido vigente actual; requiere identificar "
    "la ley igual que BUSQUEDA_POR_LEY. Usa BUSQUEDA_POR_LEY si la pregunta "
    "menciona una ley o codigo especifico por nombre pero NO pide un numero "
    "de articulo puntual ni su historial de reformas. Usa BUSQUEDA_GENERAL "
    "para cualquier otra pregunta legal de Chiapas sin ley especifica "
    "mencionada. Usa NINGUNA solo si la pregunta claramente no requiere "
    "ninguna busqueda legal (saludo, agradecimiento, despedida).\n\n"
    "Ejemplo 1:\n"
    "Pregunta: Que sanciones existen por tortura en Chiapas?\n"
    '{"accion": "BUSQUEDA_GENERAL", "ley": null, "articulo": null}\n\n'
    "Ejemplo 2:\n"
    "Pregunta: Que dice el articulo 270 del codigo penal de Chiapas?\n"
    '{"accion": "ARTICULO_ESPECIFICO", "ley": "codigo penal", "articulo": "270"}\n\n'
    "Ejemplo 3:\n"
    "Pregunta: Que dice la ley de transparencia de Chiapas sobre solicitudes de informacion?\n"
    '{"accion": "BUSQUEDA_POR_LEY", "ley": "ley de transparencia", "articulo": null}\n\n'
    "Ejemplo 4:\n"
    "Pregunta: Gracias, eso era todo\n"
    '{"accion": "NINGUNA", "ley": null, "articulo": null}\n\n'
    "Ejemplo 5:\n"
    "Pregunta: Que reformas ha tenido el Codigo de Atencion a la Familia de Chiapas?\n"
    '{"accion": "HISTORIAL_LEY", "ley": "codigo de atencion a la familia", "articulo": null}\n\n'
    "Ejemplo 6 (nombre completo -- NO acortar, ver instruccion arriba):\n"
    "Pregunta: Que dice el articulo 270 del Codigo Penal para el Estado de Chiapas?\n"
    '{"accion": "ARTICULO_ESPECIFICO", "ley": "Codigo Penal para el Estado de Chiapas", "articulo": "270"}'
)

_VALID_DECISIONS = {
    "ninguna", "busqueda_general", "busqueda_por_ley", "articulo_especifico", "historial_ley",
}
_NULLISH = {"NINGUNA", "NINGUNO", "N/A", "-", ""}

_ACCION_RE = re.compile(r"ACCION\s*:\s*(\S+)", re.IGNORECASE)
_LEY_RE = re.compile(r"LEY\s*:\s*(.+)", re.IGNORECASE)
_ARTICULO_RE = re.compile(r"ARTICULO\s*:\s*(.+)", re.IGNORECASE)


def _normalize_decision_fields(
    accion_raw: object, ley_raw: object, articulo_raw: object
) -> tuple[str, str | None, str | None] | None:
    """Normaliza y valida los 3 campos crudos (accion/ley/articulo) sin
    importar si vinieron del parser JSON o del parser regex de texto plano
    (ver _parse_decision_json/_parse_decision abajo) -- misma logica de
    downgrades seguros y de tolerancia a sufijos de articulo, centralizada
    aca para que los dos caminos de parseo no puedan divergir. Devuelve None
    si `accion_raw` no es una de las 5 acciones validas -- el llamador debe
    caer al default seguro (busqueda_general) en ese caso, nunca bloquear ni
    asumir NINGUNA."""
    if not accion_raw:
        return None
    accion = str(accion_raw).strip().lower().rstrip(".,;")
    if accion not in _VALID_DECISIONS:
        return None

    ley = str(ley_raw).strip() if ley_raw else None
    if ley and ley.upper() in _NULLISH:
        ley = None

    articulo = None
    if articulo_raw:
        articulo_clean = str(articulo_raw).strip().rstrip(".,;")
        if articulo_clean and articulo_clean.upper() not in _NULLISH:
            # Bug real encontrado y corregido (Etapa 1, ver app.rag.chunker.py
            # ARTICULO_RE para el mismo patron ya conocido): chunks.articulo_numero
            # guarda el sufijo latino cuando el articulo lo tiene ("15 Bis", "117
            # BIS", "278-A") -- son comunes en este corpus (Codigo Penal en
            # particular tiene muchos). Extraer SOLO el digito inicial (version
            # anterior de este parser) descartaba el sufijo, asi que
            # get_article() nunca encontraba estos articulos aunque existieran
            # de verdad -- un "articulo_especifico" pedido con sufijo siempre
            # caia a "no encontrado". Se preserva el numero completo (digitos +
            # sufijo/guion tal como lo escribio el LLM); get_article() compara
            # sin distinguir mayusculas/espacios para tolerar variantes de
            # formato ("15 Bis" vs "15 BIS").
            match = re.search(r"\d+[\s-]?[A-Za-z]*", articulo_clean)
            if match:
                articulo = match.group(0).strip()

    # Downgrades seguros: si la accion pedida no trae los datos que
    # necesita, se cae a busqueda_general en vez de fallar o de forzar una
    # busqueda con datos incompletos (ver docstring de modulo, invariante 2).
    if accion == "busqueda_por_ley" and not ley:
        accion = "busqueda_general"
    if accion == "articulo_especifico" and not (ley and articulo):
        accion = "busqueda_general"
    if accion == "historial_ley" and not ley:
        accion = "busqueda_general"

    return accion, ley, articulo


def _parse_decision_json(raw: str) -> tuple[str, str | None, str | None] | None:
    """Parsea el output de DECIDE_SYSTEM_PROMPT como JSON
    {"accion", "ley", "articulo"} -- se intenta PRIMERO (ver _node_decidir,
    que pide response_format={"type":"json_object"}). Devuelve None si `raw`
    no es JSON valido o no tiene forma de objeto -- el llamador cae a
    _parse_decision (regex sobre texto plano) en ese caso, para el proveedor
    que ignore response_format y devuelva texto plano de todas formas."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return _normalize_decision_fields(data.get("accion"), data.get("ley"), data.get("articulo"))


def _parse_decision(raw: str) -> tuple[str, str | None, str | None] | None:
    """Parsea el output de DECIDE_SYSTEM_PROMPT en el formato de texto plano
    ACCION:/LEY:/ARTICULO: -- red de seguridad para cuando el proveedor no
    respeta response_format (ver _parse_decision_json, que se intenta
    primero en _node_decidir). Devuelve (accion, ley_o_None, articulo_o_None),
    o None si no se pudo parsear una accion valida."""
    accion_match = _ACCION_RE.search(raw)
    ley_match = _LEY_RE.search(raw)
    articulo_match = _ARTICULO_RE.search(raw)
    return _normalize_decision_fields(
        accion_match.group(1) if accion_match else None,
        ley_match.group(1) if ley_match else None,
        articulo_match.group(1) if articulo_match else None,
    )


class AgentState(TypedDict, total=False):
    db: Session
    question: str
    conversation_history: list[dict] | None
    technical: bool
    """Switch de registro (ver app.rag.generator._ESTILO_TECNICO), elegido
    por el usuario en la UI -- solo lo lee _node_generar, no afecta ninguna
    decision de ruteo/busqueda del agente."""
    query_embedding: list[float]
    decision: str
    law_name: str | None
    articulo: str | None
    chunks: list[RetrievedChunk]
    clarification_options: list[str]
    """Fase 9.3 (coverage checker): poblado por _node_buscar SOLO en la
    ruta articulo_especifico cuando get_article devolvio None por
    AMBIGUEDAD real (2+ leyes candidatas, ver
    app.rag.agent_tools.get_article_ambiguity) -- _node_generar lo revisa
    de primero y, si esta presente, responde pidiendo aclaracion en vez de
    generar con el LLM o admitir honestamente "no encontre informacion"."""
    answer: str
    model_used: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    grounded: bool
    grounding_classifier_model: str | None
    # --- Etapa 2 (self-reflection), campos nuevos ---
    search_text: str
    """Texto usado para buscar (BM25/rerank), separado de `question` (que se
    mantiene SIEMPRE como la pregunta original del usuario -- se le muestra
    al LLM de generacion y al segundo gate de grounding tal cual, igual que
    `rag_pipeline.answer_question` hace con `search_question` vs `question`).
    Arranca igual a `question`; `_node_reformular` lo reemplaza en reintentos.
    """
    intentos: int
    """Cuantos ciclos buscar->generar ya se ejecutaron. Empieza en 0, lo
    incrementa _node_buscar en cada ejecucion (no _node_reformular) para que
    el conteo refleje intentos REALES de busqueda+generacion, no llamadas al
    LLM de reformulacion."""
    max_intentos: int
    self_reflection_enabled: bool
    grounded_gate: bool
    """El gate PRIMARIO (any(c.passed_threshold...) o len(chunks)>0 segun la
    ruta), ANTES del segundo gate de grounding -- se guarda en el estado
    para que _should_retry_after_generar pueda leerlo sin recalcularlo ni
    reinterpretar `grounded` (que ya es el resultado FINAL, post-segundo-
    gate). Ver _node_generar."""


def _node_decidir(state: AgentState) -> dict:
    question = state["question"]
    # BUG REAL (2026-08-04, auditoria de integracion LLM): antes de este fix,
    # este nodo siempre veia la pregunta CRUDA del usuario, aunque
    # answer_question_agentic ya haya resuelto referencias de contexto/typos
    # via rewrite_query en `search_text` (ver mas abajo) -- un seguimiento
    # corto tipo "Y las multas?" llegaba aca sin contexto, y "decidir" no
    # tenia forma de saber a que ley se referia. Se usa `search_text` (ya
    # resuelto contra conversation_history antes de invocar el grafo, o
    # `question` sin cambios si no hizo falta reescribir) para que la
    # decision de ruta vea lo mismo que "buscar" -- mismo criterio ya
    # aplicado en rag_pipeline.answer_question (search_question vs question).
    search_text = state.get("search_text") or question
    messages = [
        {"role": "system", "content": DECIDE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Pregunta: {search_text}"},
    ]

    decision, law_name, articulo = "busqueda_general", None, None
    try:
        raw, model_used, _, _ = generate_with_fallback(
            messages, temperature=0.0, fast=True, response_format={"type": "json_object"}
        )
        raw = raw or ""
        # JSON primero (ver DECIDE_SYSTEM_PROMPT/_parse_decision_json); si el
        # proveedor ignoro response_format y devolvio texto plano, cae al
        # parser regex original como red de seguridad.
        parsed = _parse_decision_json(raw) or _parse_decision(raw)
        if parsed is not None:
            decision, law_name, articulo = parsed
        else:
            logger.warning(
                "agente decidir: output no parseable (%r), usando busqueda_general por defecto", raw
            )
        logger.info(
            "agente decidir (%s): pregunta=%r -> accion=%s ley=%r articulo=%r",
            model_used, question, decision, law_name, articulo,
        )
    except AllModelsFailedError as exc:
        logger.warning(
            "agente decidir: todos los proveedores fallaron, usando busqueda_general por defecto: %s", exc
        )
    except Exception as exc:  # noqa: BLE001 - fallback silencioso, mismo criterio que AllModelsFailedError arriba
        logger.warning("agente decidir fallo (error inesperado), usando busqueda_general por defecto: %s", exc)

    return {"decision": decision, "law_name": law_name, "articulo": articulo}


# ---------------------------------------------------------------------------
# Nodo "buscar"
# ---------------------------------------------------------------------------


def _node_buscar(state: AgentState) -> dict:
    db = state["db"]
    # search_text (Etapa 2): en el intento 1 es igual a `question`; en un
    # reintento, _node_reformular ya lo reemplazo por la version reformulada.
    # `question` en si NUNCA cambia -- ver AgentState.search_text.
    search_text = state.get("search_text") or state["question"]
    query_embedding = state.get("query_embedding")
    decision = state.get("decision", "busqueda_general")
    intentos = state.get("intentos", 0) + 1

    if decision == "ninguna":
        return {"chunks": [], "intentos": intentos}

    if decision == "articulo_especifico":
        chunk = get_article(db, state["law_name"], state["articulo"])
        if chunk is None:
            # Fase 9.3: antes de admitir "no encontre informacion" sin mas,
            # distinguir si la razon real es AMBIGUEDAD (2+ leyes candidatas)
            # -- solo se paga esta consulta extra en el caso raro donde
            # get_article ya fallo, nunca en el camino feliz.
            ambiguous = get_article_ambiguity(db, state["law_name"], state["articulo"])
            if ambiguous:
                return {"chunks": [], "intentos": intentos, "clarification_options": ambiguous}
        return {"chunks": [chunk] if chunk is not None else [], "intentos": intentos}

    if decision == "historial_ley":
        # Fase 8 (GraphRAG): consulta legal_relations en vez de retrieval
        # semantico -- ver app.rag.agent_tools.query_graph/relations_to_chunks
        # y la nota de la ruta en el docstring de modulo (invariante 6). Se
        # pasa el articulo (si el LLM de "decidir" lo detecto en la
        # pregunta, ej. "que le paso al articulo 93 de X") para que
        # query_graph filtre EXACTO por ese articulo en vez de traer solo
        # las relaciones mas recientes de TODA la ley -- ver el docstring de
        # query_graph para el bug real que esto corrige (el articulo pedido
        # podia quedar fuera del top-K ordenado por fecha si la ley tenia
        # muchas relaciones mas recientes en OTROS articulos).
        relations = query_graph(db, state["law_name"], articulo=state.get("articulo"))
        return {"chunks": relations_to_chunks(relations), "intentos": intentos}

    # Fase 9.8 (C6): expansion de sinonimos legales, SOLO en las ramas de
    # busqueda semantica (general/por-ley). Portada de
    # rag_pipeline.answer_question (Fase 3.7): consultas coloquiales que no
    # comparten vocabulario con el articulo que las responde (ej. "sin
    # testamento" vs. el termino legal "sucesion legitima"). Se aplica sobre
    # search_text (no sobre `question`, que sigue crudo para el ranking de
    # citas) y se re-embebe solo si de verdad expandio, igual patron que el
    # pipeline lineal -- no toca las rutas articulo_especifico/historial_ley,
    # que resuelven por nombre/numero exacto y no se benefician de sinonimos.
    search_text, was_expanded = expand_legal_synonyms(search_text)
    if was_expanded:
        query_embedding = embed_text(search_text)

    if decision == "busqueda_por_ley":
        # Etapa 2: en un reintento se mantiene el MISMO law_name que decidio
        # el nodo "decidir" en el intento 1 -- ver _node_reformular para por
        # que el reintento NUNCA cambia de ruta (busqueda_por_ley <->
        # busqueda_general), solo el texto de busqueda dentro de la MISMA ruta.
        chunks = search_by_law(db, state["law_name"], search_text, query_embedding=query_embedding)
        return {"chunks": chunks, "intentos": intentos}

    # busqueda_general y cualquier valor no reconocido: mismo comportamiento
    # del pipeline lineal (hybrid_search + rerank sin filtro de ley).
    chunks = search_laws(db, search_text, query_embedding=query_embedding)
    return {"chunks": chunks, "intentos": intentos}


# ---------------------------------------------------------------------------
# Nodo "generar"
# ---------------------------------------------------------------------------


def _node_generar(state: AgentState) -> dict:
    question = state["question"]
    conversation_history = state.get("conversation_history")
    technical = state.get("technical", False)
    chunks = state.get("chunks") or []
    decision = state.get("decision", "busqueda_general")

    # Fase 9.3 (coverage checker): un tercer camino ademas de
    # responder/admitir-no-encontrado -- pedir aclaracion cuando
    # _node_buscar detecto ambiguedad real de nombre de ley (ver
    # AgentState.clarification_options). Deterministico, SIN llamar al LLM
    # principal -- no hay nada que generar, solo listar las opciones reales
    # que get_article_ambiguity ya encontro en la DB. grounded=False porque
    # esto no es una respuesta fundamentada, es una pregunta de vuelta;
    # nunca reintenta (articulo_especifico esta fuera de la lista blanca de
    # _should_retry_after_generar, invariante 3 del docstring de modulo).
    clarification_options = state.get("clarification_options")
    if clarification_options:
        opciones = "; ".join(clarification_options)
        answer = (
            f"{CLARIFICATION_QUESTION_MARKER}: {opciones}. "
            "¿Podrias decirme cual de estas es la que te interesa?"
        )
        return {
            "answer": answer,
            "model_used": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "grounded": False,
            "grounding_classifier_model": None,
            "grounded_gate": False,
        }

    if decision in ("articulo_especifico", "historial_ley"):
        # Gate anti-alucinacion PROPIO de estas rutas (ver decision de diseno
        # completa en app.rag.agent_tools.get_article para articulo_especifico,
        # y query_graph/relations_to_chunks para historial_ley -- Fase 8): los
        # chunks vienen de un lookup EXACTO (por documento+numero de articulo,
        # o por relaciones reales en legal_relations), no de similitud
        # semantica, asi que passed_threshold (que solo dense_search puede
        # poner) siempre es False aqui por diseno y NO es indicativo de nada
        # en estas rutas. El criterio real: se encontro contenido real en la
        # DB (articulo exacto, o al menos una relacion real) o no.
        grounded_gate = len(chunks) > 0
    else:
        # Mismo gate real que rag_pipeline.answer_question, sin modificar:
        # solo un chunk que REALMENTE paso el threshold de similitud coseno
        # de dense_search puede fundamentar una respuesta. BM25 nunca pone
        # passed_threshold=True (ver retriever.RetrievedChunk).
        grounded_gate = any(c.passed_threshold for c in chunks)

    answer, model_used, prompt_tokens, completion_tokens = generate_answer(
        question, chunks if grounded_gate else [], conversation_history=conversation_history, technical=technical
    )

    grounded = grounded_gate
    grounding_classifier_model = None
    if grounded:
        # Segundo gate (Fase 3.7), identico al pipeline lineal: solo puede
        # degradar True a False, nunca al reves. Se aplica sin importar que
        # ruta tomo el agente (invariante 4 del docstring de modulo).
        grounded, grounding_classifier_model = answer_is_grounded_in_practice(
            question, answer, chunks
        )

    return {
        "answer": answer,
        "model_used": model_used,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "grounded": grounded,
        "grounding_classifier_model": grounding_classifier_model,
        # Etapa 2: se guarda el gate PRIMARIO (pre-segundo-gate) por
        # separado de `grounded` (que ya es el resultado final) -- lo
        # necesita _should_retry_after_generar para decidir si vale la pena
        # reintentar (ver docstring de esa funcion).
        "grounded_gate": grounded_gate,
    }


# ---------------------------------------------------------------------------
# Nodo "reformular" (Etapa 2, self-reflection)
# ---------------------------------------------------------------------------

REFORMULATE_SYSTEM_PROMPT = (
    "Ayudas a mejorar una busqueda de textos legales de Chiapas, Mexico. Un "
    "primer intento de busqueda con la consulta de abajo NO encontro "
    "pasajes que respondieran bien la pregunta del usuario. Reformula la "
    "consulta de busqueda como una version ALTERNATIVA, breve, en espanol, "
    "usando terminologia legal distinta a la original -- sinonimos "
    "juridicos, el nombre tecnico de la institucion legal en vez de "
    "lenguaje coloquial, o una formulacion mas general o mas especifica "
    "segun convenga. NO inventes el nombre de una ley, codigo o articulo "
    "que no conozcas con certeza -- si no se te ocurre una reformulacion "
    "genuinamente distinta que valga la pena probar, responde EXACTAMENTE "
    "con la misma consulta original sin cambios. Responde SOLO con la "
    "consulta (original o reformulada), una sola linea, sin explicaciones, "
    "sin comillas, sin markdown."
)


def _reformulate_search_text(question: str, previous_search_text: str, previous_chunks: list[RetrievedChunk]) -> str:
    """Devuelve una consulta de busqueda alternativa, o `previous_search_text`
    sin cambios si la llamada falla o el LLM no propone nada distinto.

    Fallback seguro (mismo principio que app.rag.query_rewriting.
    rewrite_query / app.rag.hyde.generate_hypothetical_answer): esto es una
    optimizacion de retrieval, nunca debe bloquear el pipeline -- si falla,
    el llamador reintenta la busqueda con el MISMO texto (equivalente a no
    tener self-reflection para ese intento particular, no un error fatal).
    """
    chunks_summary = "; ".join(
        f"{c.document_nombre} Art. {c.articulo_numero}" for c in (previous_chunks or [])[:5]
    ) or "(ningun pasaje relevante)"
    user_content = (
        f"Pregunta original del usuario: {question}\n"
        f"Consulta de busqueda anterior: {previous_search_text}\n"
        f"Pasajes que encontro esa consulta (no respondieron bien): {chunks_summary}\n"
        "Consulta reformulada:"
    )
    messages = [
        {"role": "system", "content": REFORMULATE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        raw, model_used, _, _ = generate_with_fallback(messages, temperature=0.3, fast=True)
        reformulated = (raw or "").strip()
        if not reformulated:
            return previous_search_text
        logger.info(
            "agente reformular (%s): %r -> %r", model_used, previous_search_text, reformulated
        )
        return reformulated
    except AllModelsFailedError as exc:
        logger.warning(
            "agente reformular: todos los proveedores fallaron, reintentando con el mismo texto: %s", exc
        )
        return previous_search_text
    except Exception as exc:  # noqa: BLE001 - fallback silencioso, ver docstring
        logger.warning("agente reformular fallo (error inesperado), reintentando con el mismo texto: %s", exc)
        return previous_search_text


def _node_reformular(state: AgentState) -> dict:
    question = state["question"]
    previous_search_text = state.get("search_text") or question
    previous_chunks = state.get("chunks") or []

    new_search_text = _reformulate_search_text(question, previous_search_text, previous_chunks)
    if new_search_text == previous_search_text:
        # BUG REAL (auditoria de calidad de codigo, 2026-08-06):
        # _reformulate_search_text puede devolver el mismo texto sin cambios
        # (el LLM no encontro una reformulacion genuinamente distinta, o la
        # llamada fallo -- ver su docstring) -- en ese caso el embedding ya
        # calculado para ese mismo texto sigue siendo valido, no vale la
        # pena pagar otra llamada real a NVIDIA solo para recalcular lo
        # mismo.
        return {"search_text": new_search_text, "query_embedding": state.get("query_embedding")}

    new_query_embedding = embed_text(new_search_text)
    return {"search_text": new_search_text, "query_embedding": new_query_embedding}


# ---------------------------------------------------------------------------
# Grafo
# ---------------------------------------------------------------------------


def _should_retry_after_generar(state: AgentState) -> str:
    """Decide si volver a "reformular" (retry) o terminar en END, DESPUES de
    "generar". Solo se registra como conditional edge si self-reflection
    esta habilitado (ver _build_graph) -- con la bandera apagada el grafo ni
    siquiera tiene este nodo/rama, cero cambio de comportamiento vs. Etapa 1.

    CUANDO SI reintenta (los 4 deben cumplirse):
    1. La ruta fue busqueda_general o busqueda_por_ley -- articulo_especifico,
       historial_ley (Fase 8, GraphRAG, ver invariante 6) y ninguna NUNCA
       reintentan (invariante 3 del docstring de modulo: no hay ambiguedad de
       fraseo que una reformulacion pueda resolver en un lookup exacto por
       clave). Esto se cumple SIN tocar esta condicion: la lista blanca de
       abajo solo nombra busqueda_general/busqueda_por_ley, asi que
       historial_ley (o cualquier decision futura) cae fuera automaticamente.
    2. `grounded_gate` (el gate PRIMARIO, pre-segundo-gate) fue True -- es
       decir, dense_search SI encontro chunks que pasaron el threshold real
       de similitud, y por lo tanto SI se llego a generar una respuesta con
       contenido real. Si `grounded_gate` ya era False (nada paso el
       threshold, ni siquiera se llamo al LLM principal), NO se reintenta.
    3. `grounded` final (post-segundo-gate) es False -- el caso real medido
       esta sesion: el segundo gate (answer_is_grounded_in_practice) detecto
       que los chunks eran de OTRA ley/tema y degrado el resultado.
    4. `intentos` < `max_intentos` -- tope duro, nunca mas de 1 reintento
       con max_intentos=2 (default).

    POR QUE LA CONDICION 2 IMPORTA TANTO (evidencia real, no supuesta): se
    midio en vivo esta sesion que las 3 preguntas "no encontrado con falso
    positivo" documentadas en PLAN.md Fase 3.7 (consumidor, ley federal del
    trabajo, proteccion animal) YA terminan con `grounded_gate=False` desde
    el intento 1 dentro del AGENTE (no del pipeline lineal) -- el nodo
    "decidir" identifica el nombre de ley mencionado explicitamente en la
    pregunta y toma la ruta busqueda_por_ley, cuyo document_filter (ILIKE
    sobre documents.nombre) no matchea ningun documento real para esos 3
    casos, asi que hybrid_search devuelve chunks=[] de entrada -- sin llamar
    siquiera al LLM principal. Se probo en vivo (search_laws() directo, sin
    el filtro por ley) que SI ESTAS 3 PREGUNTAS SE BUSCARAN CON
    busqueda_general EN VEZ DE busqueda_por_ley, 2 de las 3 (consumidor,
    proteccion animal) SI cruzan similarity_threshold=0.5 con chunks de
    OTRAS leyes (Ley de Salud, Codigo Civil, Codigo Fiscal para consumidor;
    Codigo Penal Art.494/495 y Ley de Salud Art.228 para animal) -- el mismo
    patron de falso positivo ya documentado (Fase 3.7, bucket B) para el
    pipeline lineal. Esto es evidencia real y medida de que reintentar
    CAMBIANDO de ruta (de busqueda_por_ley a busqueda_general, la opcion (a)
    evaluada en el diseno) cuando el gate primario ya fue False
    REINTRODUCIRIA el mismo riesgo de alucinacion por lenguaje generico que
    la ruta busqueda_por_ley ya evita gratis -- por eso el reintento de
    Etapa 2 NUNCA cambia de ruta, solo reformula el TEXTO de busqueda dentro
    de la MISMA ruta (opcion (b) del diseno, ver _node_reformular), y NUNCA
    se activa cuando el gate primario ya fue False desde el intento 1.
    """
    if state.get("decision") not in ("busqueda_general", "busqueda_por_ley"):
        return END
    if not state.get("grounded_gate", False):
        return END
    if state.get("grounded", False):
        return END
    if state.get("intentos", 0) >= state.get("max_intentos", 2):
        return END
    return "reformular"


def _build_graph(self_reflection_enabled: bool):
    workflow = StateGraph(AgentState)
    workflow.add_node("decidir", _node_decidir)
    workflow.add_node("buscar", _node_buscar)
    workflow.add_node("generar", _node_generar)
    workflow.add_edge(START, "decidir")
    workflow.add_edge("decidir", "buscar")
    workflow.add_edge("buscar", "generar")

    if self_reflection_enabled:
        # Etapa 2: unico ciclo del grafo, con tope duro garantizado por
        # _should_retry_after_generar (intentos < max_intentos) -- LangGraph
        # no tiene un limite de recursion propio configurado aqui a
        # proposito, el limite real vive en la condicion misma, no en
        # infraestructura aparte, para que quede legible en un solo lugar.
        workflow.add_node("reformular", _node_reformular)
        workflow.add_conditional_edges(
            "generar", _should_retry_after_generar, {"reformular": "reformular", END: END}
        )
        workflow.add_edge("reformular", "buscar")
    else:
        # Etapa 1, comportamiento identico a antes: grafo lineal sin ciclos.
        workflow.add_edge("generar", END)

    return workflow.compile()


_compiled_graphs: dict[bool, object] = {}


def _get_graph(self_reflection_enabled: bool):
    """Compila el grafo una sola vez por proceso Y por valor de
    self_reflection_enabled (igual criterio que el cache de indice BM25 en
    app.rag.retriever -- compilar en cada pregunta seria trabajo repetido
    innecesario; el grafo en si no tiene estado mutable entre invocaciones,
    invoke() recibe su propio AgentState).

    Correccion (auditoria de calidad de codigo, 2026-08-06): el docstring
    anterior decia que ai_config.json "se puede recargar en caliente" -- eso
    es incorrecto. get_ai_config() (app/config.py) esta decorado con
    @lru_cache SIN argumentos y nada en el repo llama a su .cache_clear(),
    asi que en la practica el archivo se lee UNA sola vez por proceso; un
    cambio en ai_config.json requiere reiniciar el proceso para tomar
    efecto, igual que Settings. Con eso, self_reflection_enabled tambien es
    constante durante la vida del proceso, y este dict nunca va a tener mas
    de una entrada real en produccion -- se mantiene parametrizado por bool
    de todas formas porque es igual de simple que hardcodear un solo cache
    y no asume nada sobre el orden de llamadas.
    """
    if self_reflection_enabled not in _compiled_graphs:
        _compiled_graphs[self_reflection_enabled] = _build_graph(self_reflection_enabled)
    return _compiled_graphs[self_reflection_enabled]


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def answer_question_agentic(
    db: Session,
    question: str,
    conversation_history: list[dict] | None = None,
    technical: bool = False,
) -> tuple[ChatResponse, int]:
    """MISMA firma que rag_pipeline.answer_question, para poder
    intercambiarlas via ai_config.json "agentic_rag.enabled" (ver
    app.bots.conversation_store.handle_turn). `technical` se inyecta tal
    cual en el AgentState inicial, solo lo usa _node_generar.

    Optimizaciones portadas del pipeline lineal:
    - Query rewriting (app.rag.query_rewriting.rewrite_query, agregado
      2026-08-04, ver BUG REAL mas abajo): sin esto un seguimiento corto en
      una conversacion llegaba SIN CONTEXTO tanto a "decidir" como a
      "buscar".
    - Cache semantico (app.rag.semantic_cache, Fase 9.8/C6): lookup al inicio
      (solo preguntas sin historial) y store al final, igual criterio que
      rag_pipeline.answer_question. Antes estaba MUERTO en esta ruta pese a
      semantic_cache.enabled=true -- con agentic_rag.enabled=true en
      produccion, ninguna pregunta pagaba/poblaba el cache. Seguro ante
      cambio de modelo de embeddings via la columna embedding_model (C5).
    - Expansion de sinonimos legales (app.rag.legal_synonyms, Fase 9.8/C6):
      aplicada en _node_buscar sobre las rutas de busqueda semantica.
    HyDE NO se porta (medido que empeora retrieval con el modelo de
    embeddings actual, ver ai_config.json "hyde._note_migracion_2026_08_27").
    Capa 1 de guardrails y ambos gates anti-alucinacion se preservan sin
    excepcion desde el inicio (ver invariantes en el docstring de modulo).

    Etapa 2 (self-reflection, ver docstring de modulo): bandera
    `ai_config.json` "agentic_rag.self_reflection.enabled" (default False) +
    "max_intentos" (default 2) -- se leen aqui, UNA vez por pregunta, y se
    inyectan en el AgentState inicial para que _should_retry_after_generar
    las use sin volver a leer el archivo de config en medio del grafo.
    """
    start = time.monotonic()

    # Small talk: mismo criterio que rag_pipeline.answer_question (ver ese
    # comentario para el hallazgo real completo) -- corre antes que
    # cualquier otra cosa, incluida la lectura de ai_config.json.
    smalltalk_response = detect_smalltalk_response(question)
    if smalltalk_response is not None:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        response = ChatResponse(
            answer=smalltalk_response,
            retrieved_chunks=[],
            llm_model=None,
            grounded=False,
            prompt_tokens=None,
            completion_tokens=None,
        )
        return response, elapsed_ms

    ai_config = get_ai_config()
    self_reflection_config = ai_config.get("agentic_rag", {}).get("self_reflection", {})
    self_reflection_enabled = self_reflection_config.get("enabled", False)
    max_intentos = self_reflection_config.get("max_intentos", 2)

    query_embedding = embed_text(question)

    # Capa 1 de guardrails: identica al pipeline lineal (ver
    # rag_pipeline.answer_question para el bug real que motivo el gate por
    # conversation_history), corre FUERA del control del agente (invariante 1).
    in_scope = True
    if not conversation_history:
        in_scope, _ = classify_intent(question, question_embedding=query_embedding)
    if not in_scope:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        response = ChatResponse(
            answer=OUT_OF_SCOPE_MESSAGE,
            retrieved_chunks=[],
            llm_model=None,
            grounded=False,
            prompt_tokens=None,
            completion_tokens=None,
        )
        return response, elapsed_ms

    # Cache semantico (Fase 9.8/C6, ver app.rag.semantic_cache): SOLO para
    # preguntas sin historial (un seguimiento corto depende del contexto de
    # ESA conversacion, no cacheable por similitud de embedding sola). Se usa
    # el embedding de la pregunta ORIGINAL (antes de rewrite/sinonimos) para
    # que lookup y store comparen sobre la misma base -- identico criterio que
    # rag_pipeline.answer_question.
    original_query_embedding = query_embedding
    if not conversation_history:
        cached = cache_lookup(db, original_query_embedding)
        if cached is not None:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # search_time_ms/generation_time_ms del objeto cacheado reflejan
            # CUANDO SE GENERO originalmente, no este hit (mismo reset que el
            # pipeline lineal, para no contaminar avg/p95 de /admin/metrics).
            cached = cached.model_copy(update={"search_time_ms": None, "generation_time_ms": None})
            return cached, elapsed_ms

    # BUG REAL (2026-08-04, auditoria de integracion LLM): esta linea antes
    # ponia `search_text` = `question` sin cambios -- el agente (a diferencia
    # de rag_pipeline.answer_question, que ya llama rewrite_query desde Fase
    # 6) nunca resolvia referencias de contexto conversacional ni typos antes
    # de decidir ruta o buscar. Con agentic_rag.enabled=true ya en
    # produccion, esto degradaba cualquier seguimiento corto en una
    # conversacion ("Y las multas?") a una busqueda literal de ese texto
    # sin contexto, casi siempre sin pasar el threshold real -- el mismo bug
    # que rewrite_query fue creado para resolver, pero nunca portado aca.
    # Mismo patron que rag_pipeline.answer_question: solo se recalcula el
    # embedding si de verdad se reescribio algo, para no gastar una llamada
    # de mas cuando no hace falta.
    search_text, was_rewritten = rewrite_query(question, conversation_history)
    if was_rewritten:
        query_embedding = embed_text(search_text)

    initial_state: AgentState = {
        "db": db,
        "question": question,
        "conversation_history": conversation_history,
        "technical": technical,
        "query_embedding": query_embedding,
        "search_text": search_text,
        "intentos": 0,
        "max_intentos": max_intentos,
        "self_reflection_enabled": self_reflection_enabled,
    }
    final_state = _get_graph(self_reflection_enabled).invoke(initial_state)

    chunks = final_state.get("chunks") or []
    elapsed_ms = int((time.monotonic() - start) * 1000)

    response = ChatResponse(
        answer=final_state["answer"],
        retrieved_chunks=[
            RetrievedChunkSchema(
                chunk_id=c.chunk_id,
                document_nombre=c.document_nombre,
                articulo_numero=c.articulo_numero,
                similarity=c.similarity,
                content=c.content,
                passed_threshold=c.passed_threshold,
                derogado=is_articulo_derogado(c.content),
                historial=get_articulo_historial(db, c.document_nombre, c.articulo_numero),
            )
            for c in chunks
        ],
        llm_model=final_state.get("model_used"),
        grounded=final_state.get("grounded", False),
        prompt_tokens=final_state.get("prompt_tokens"),
        completion_tokens=final_state.get("completion_tokens"),
        grounding_classifier_model=final_state.get("grounding_classifier_model"),
        agent_trace=AgentTrace(
            route=final_state.get("decision", "ninguna"),
            law_name=final_state.get("law_name"),
            articulo=final_state.get("articulo"),
            intentos=final_state.get("intentos", 0),
            self_reflection_triggered=final_state.get("intentos", 0) > 1,
        ),
    )

    # Cache store (Fase 9.8/C6): mismo criterio que lookup arriba y que
    # rag_pipeline.answer_question -- solo preguntas sin historial, con el
    # embedding de la pregunta ORIGINAL. Se cachean grounded True y False
    # (una pregunta fuera del corpus tambien cuesta busqueda cada vez).
    if not conversation_history:
        cache_store(db, question, original_query_embedding, response)

    return response, elapsed_ms
