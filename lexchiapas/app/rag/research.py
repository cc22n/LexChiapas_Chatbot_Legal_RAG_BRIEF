"""Modo investigacion ("Investigar a fondo", LexChiapas_Plan_Agente_Investigacion.md
10.3 y seccion 5).

Ruta ADICIONAL, pedida por pregunta (WebChatRequest.research) y apagada por
defecto (ai_config.json agentic_rag.research.enabled). No reemplaza al pipeline
lineal ni al agentico. Flujo:

    smalltalk / Capa 1 (igual que los demas pipelines, fuera del control del modo)
    -> planificar   (1 LLM barato: 2-3 subpreguntas + areas del derecho)
    -> buscar       (hybrid_search por la pregunta y cada subpregunta, sin LLM)
    -> unir         (dedupe por fragmento) y reordenar UNA vez con top_k mayor
    -> sintetizar   (1 generacion con estructura fija: que dice, como aplica,
                     excepciones/reformas/derogaciones, que no cubre)
    -> segundo gate (1 LLM) + guardia de relleno

Invariantes (plan seccion 4): el gate primario sigue siendo "algun fragmento
supero el umbral de similitud"; el segundo gate nunca se relaja; las citas y el
disclaimer los pone el generador; tope duro de llamadas LLM (max_llm_calls, con
minimo efectivo de 3 porque generar y verificar no se pueden omitir) y de
subpreguntas (max_subquestions); la conexion de BD se libera antes de cada
llamada externa.
"""

import json
import logging
import re
import time

from sqlalchemy.orm import Session

from app.config import get_ai_config
from app.llm.providers import embed_text
from app.llm.router import AllModelsFailedError, generate_with_fallback
from app.llm.token_usage import begin_usage, get_usage
from app.rag.agent_tools import get_articulos_historial_bulk
from app.rag.db_session import release_connection
from app.rag.filler_guard import strip_unsupported_filler
from app.rag.generator import generate_answer
from app.rag.grounding import answer_is_grounded_in_practice
from app.rag.guardrails import OUT_OF_SCOPE_MESSAGE, classify_intent, detect_smalltalk_response
from app.rag.legal_synonyms import expand_legal_synonyms
from app.rag.reranker import rerank
from app.rag.retriever import RetrievedChunk, hybrid_search
from app.rag.vigencia import is_articulo_derogado
from app.schemas.chat import AgentTrace, ChatResponse, ResearchTrace
from app.schemas.chat import RetrievedChunk as RetrievedChunkSchema

logger = logging.getLogger("lexchiapas.research")

DEFAULT_MAX_SUBQUESTIONS = 3
DEFAULT_MAX_LLM_CALLS = 4
DEFAULT_TOP_K = 8
MIN_LLM_CALLS = 3  # planificar + generar + segundo gate
MAX_SUBQUESTION_CHARS = 300

RESEARCH_PLAN_SYSTEM_PROMPT = (
    "Ayudas a planificar la busqueda de una pregunta juridica sobre leyes del "
    "Estado de Chiapas, Mexico. Descompon la pregunta en 2 o 3 subpreguntas "
    "CORTAS, autonomas y distintas entre si, cada una enfocada en un aspecto "
    "legal concreto que haya que buscar por separado (por ejemplo: quien tiene "
    "la obligacion, cual es el procedimiento o plazo, cual es la sancion o la "
    "excepcion). No inventes nombres de leyes ni de articulos. Si la pregunta "
    "ya es simple y de un solo aspecto, devuelve una sola subpregunta. Indica "
    "tambien las areas del derecho implicadas (civil, penal, fiscal, laboral, "
    "administrativo, ambiental, familiar, etc.). Responde SOLO con un objeto "
    "JSON, sin markdown, con esta forma exacta: "
    '{"subpreguntas": ["...", "..."], "areas": ["...", "..."]}'
)


def _research_config() -> dict:
    return get_ai_config().get("agentic_rag", {}).get("research", {})


def parse_plan(raw: str | None, question: str, max_subquestions: int) -> tuple[list[str], list[str]]:
    """Parsea la salida del planificador de forma tolerante. Ante cualquier
    problema devuelve ([], []) y el llamador sigue solo con la pregunta
    original: planificar es una optimizacion de busqueda, nunca debe bloquear
    el turno."""
    if not raw:
        return [], []
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return [], []
    if not isinstance(data, dict):
        return [], []
    seen = {question.strip().lower()}
    subs: list[str] = []
    raw_subs = data.get("subpreguntas")
    for item in raw_subs if isinstance(raw_subs, list) else []:
        if not isinstance(item, str):
            continue
        clean = " ".join(item.split())[:MAX_SUBQUESTION_CHARS]
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            subs.append(clean)
        if len(subs) >= max_subquestions:
            break
    raw_areas = data.get("areas")
    areas = [a.strip().lower() for a in (raw_areas if isinstance(raw_areas, list) else []) if isinstance(a, str) and a.strip()][:6]
    return subs, areas


def plan_research(question: str, max_subquestions: int) -> tuple[list[str], list[str]]:
    """Una llamada LLM barata (fast=True, JSON). ([], []) si falla."""
    messages = [
        {"role": "system", "content": RESEARCH_PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        raw, model_used, _, _ = generate_with_fallback(
            messages, temperature=0.0, fast=True, response_format={"type": "json_object"}
        )
    except AllModelsFailedError as exc:
        logger.warning("investigacion: todos los proveedores fallaron al planificar: %s", exc)
        return [], []
    except Exception as exc:  # noqa: BLE001 - planificar nunca debe tumbar el turno
        logger.warning("investigacion: fallo inesperado al planificar: %s", exc)
        return [], []
    subs, areas = parse_plan(raw, question, max_subquestions)
    logger.info("investigacion (%s): %r -> %r areas=%r", model_used, question, subs, areas)
    return subs, areas


def merge_candidates(result_lists: list[list[RetrievedChunk]]) -> list[RetrievedChunk]:
    """Une los resultados de varias busquedas sin repetir fragmentos. Si un
    fragmento aparece en mas de una, conserva la mayor similitud y que haya
    pasado el umbral en cualquiera de ellas (passed_threshold es del dense real)."""
    merged: dict[int, RetrievedChunk] = {}
    for results in result_lists:
        for chunk in results:
            current = merged.get(chunk.chunk_id)
            if current is None:
                merged[chunk.chunk_id] = chunk
                continue
            current.similarity = max(current.similarity, chunk.similarity)
            current.passed_threshold = current.passed_threshold or chunk.passed_threshold
    return list(merged.values())


_NOT_COVERED_LABEL = "Que no cubre"


def apply_filler_guard(answer: str) -> tuple[str, bool]:
    """Guardia de relleno adaptada a la estructura de cuatro rotulos: la
    admision de falta de informacion se busca solo en el primer parrafo ('Que
    dice la ley') y el cuarto ('Que no cubre esta respuesta') nunca se toca,
    porque por diseno admite lo que falta. Sin esto, la frase fija del tercer
    rotulo ('No encontre excepciones ni reformas en los fragmentos') hacia que
    cualquier 'generalmente' degradara respuestas validas."""
    parts = answer.split("\n\n")
    cut = next((i for i, p in enumerate(parts) if _NOT_COVERED_LABEL in p[:40]), len(parts))
    core, rest = parts[:cut], parts[cut:]
    if not core:
        return answer, False
    cleaned, padded = strip_unsupported_filler("\n\n".join(core), admission_scope=core[0])
    if not padded:
        return answer, False
    return "\n\n".join([cleaned] + rest), True


def _to_schema_chunks(db: Session, chunks: list[RetrievedChunk]) -> list[RetrievedChunkSchema]:
    historiales = get_articulos_historial_bulk(db, [(c.document_nombre, c.articulo_numero) for c in chunks])
    return [
        RetrievedChunkSchema(
            chunk_id=c.chunk_id,
            document_nombre=c.document_nombre,
            articulo_numero=c.articulo_numero,
            similarity=c.similarity,
            content=c.content,
            passed_threshold=c.passed_threshold,
            derogado=is_articulo_derogado(c.content),
            historial=historiales.get((c.document_nombre, c.articulo_numero), []),
        )
        for c in chunks
    ]


def answer_question_research(
    db: Session,
    question: str,
    conversation_history: list[dict] | None = None,
    technical: bool = False,
) -> tuple[ChatResponse, int]:
    """Misma firma que rag_pipeline.answer_question (db, question, ...) ->
    (ChatResponse, tiempo_ms). `technical` se ignora: el modo investigacion
    usa su propio registro (simple, con terminos tecnicos glosados)."""
    start = time.monotonic()
    begin_usage()
    cfg = _research_config()
    max_subquestions = int(cfg.get("max_subquestions", DEFAULT_MAX_SUBQUESTIONS))
    max_llm_calls = int(cfg.get("max_llm_calls", DEFAULT_MAX_LLM_CALLS))
    top_k = int(cfg.get("top_k", DEFAULT_TOP_K))

    smalltalk = detect_smalltalk_response(question)
    if smalltalk is not None:
        return ChatResponse(answer=smalltalk, retrieved_chunks=[], grounded=False), int((time.monotonic() - start) * 1000)

    # Capa 1 corre fuera del control del modo (invariante 1) y solo en el primer turno.
    query_embedding = embed_text(question)
    if not conversation_history:
        in_scope, _ = classify_intent(question, question_embedding=query_embedding)
        if not in_scope:
            return (
                ChatResponse(answer=OUT_OF_SCOPE_MESSAGE, retrieved_chunks=[], grounded=False),
                int((time.monotonic() - start) * 1000),
            )

    # Planificar: 1 llamada LLM. Con un tope menor al minimo (generar + verificar
    # no se pueden omitir) se renuncia a planificar en vez de relajar el gate.
    llm_calls = 0
    subquestions: list[str] = []
    areas: list[str] = []
    release_connection(db)
    if max_llm_calls >= MIN_LLM_CALLS and max_subquestions > 0:
        subquestions, areas = plan_research(question, max_subquestions)
        llm_calls += 1

    # Buscar: la pregunta original (embedding ya calculado) y cada subpregunta.
    result_lists: list[list[RetrievedChunk]] = []
    for index, sub_query in enumerate([question] + subquestions):
        search_text, _ = expand_legal_synonyms(sub_query)
        embedding = query_embedding if (index == 0 and search_text == question) else embed_text(search_text)
        result_lists.append(hybrid_search(db, search_text, embedding))
    candidates = merge_candidates(result_lists)
    release_connection(db)  # el reranker es una llamada externa

    rerank_query = " ".join([question] + subquestions)[:600]
    top_chunks = rerank(rerank_query, candidates, top_k=top_k)
    search_time_ms = int((time.monotonic() - start) * 1000)

    # Gate primario (invariante 2): solo un fragmento que supero el umbral real puede fundamentar.
    grounded = any(c.passed_threshold for c in top_chunks)
    release_connection(db)
    generation_start = time.monotonic()
    answer, model_used, _, _ = generate_answer(
        question,
        top_chunks if grounded else [],
        conversation_history=conversation_history,
        research=True,
    )
    generation_time_ms = int((time.monotonic() - generation_start) * 1000)
    if model_used is not None:
        llm_calls += 1

    grounding_classifier_model = None
    if grounded:
        grounded, grounding_classifier_model = answer_is_grounded_in_practice(question, answer, top_chunks)
        llm_calls += 1
    if grounded:
        answer, padded = apply_filler_guard(answer)
        if padded:
            grounded = False

    gen_prompt, gen_completion, aux_prompt, aux_completion = get_usage()
    elapsed_ms = int((time.monotonic() - start) * 1000)
    schema_chunks = _to_schema_chunks(db, top_chunks)
    return (
        ChatResponse(
            answer=answer,
            retrieved_chunks=schema_chunks,
            llm_model=model_used,
            grounded=grounded,
            prompt_tokens=gen_prompt or None,
            completion_tokens=gen_completion or None,
            aux_prompt_tokens=aux_prompt or None,
            aux_completion_tokens=aux_completion or None,
            grounding_classifier_model=grounding_classifier_model,
            search_time_ms=search_time_ms,
            generation_time_ms=generation_time_ms,
            agent_trace=AgentTrace(route="investigar", intentos=1, self_reflection_triggered=False),
            research=ResearchTrace(
                subquestions=subquestions,
                areas=areas,
                llm_calls=llm_calls,
                documents_consulted=sorted({c.document_nombre for c in top_chunks}),
            ),
        ),
        elapsed_ms,
    )
