import time

from sqlalchemy.orm import Session

from app.config import get_ai_config
from app.llm.providers import embed_text
from app.rag.generator import generate_answer
from app.rag.grounding import answer_is_grounded_in_practice
from app.rag.guardrails import OUT_OF_SCOPE_MESSAGE, classify_intent, detect_smalltalk_response
from app.rag.hyde import generate_hypothetical_answer
from app.rag.legal_synonyms import expand_legal_synonyms
from app.rag.query_rewriting import rewrite_query
from app.rag.reranker import rerank
from app.rag.retriever import hybrid_search
from app.rag.semantic_cache import lookup as cache_lookup, store as cache_store
from app.rag.vigencia import is_articulo_derogado
from app.schemas.chat import ChatResponse, RetrievedChunk as RetrievedChunkSchema


def answer_question(
    db: Session,
    question: str,
    conversation_history: list[dict] | None = None,
    technical: bool = False,
) -> tuple[ChatResponse, int]:
    """Corre el pipeline completo: Capa 1 (alcance) -> query rewriting ->
    hybrid search -> threshold -> rerank -> generacion.

    technical: switch de registro (ver app.rag.generator._ESTILO_TECNICO)
    elegido por el usuario en la UI -- solo afecta la instruccion de
    generacion, retrieval/threshold/rerank son identicos sin importar su
    valor.

    conversation_history: turnos previos de la MISMA conversacion ya
    persistidos, formato [{"role": "user"|"assistant", "content": str}, ...]
    en orden cronologico. Se usa en dos lugares distintos:
    - Fase 6 (query rewriting): si `question` es corta y ambigua (ej. "Y las
      multas?"), se reescribe a una consulta auto-contenida ANTES de
      embeber/buscar, usando el ultimo turno de usuario como contexto (ver
      app.rag.query_rewriting). Esto es lo que arregla retrieval para
      seguimientos -- Fase 2.6 por si sola solo alimentaba el prompt de
      generacion, no la busqueda.
    - Fase 2.6 (memoria): se insertan en el prompt entre el system prompt y
      la pregunta actual (ver app.rag.generator.build_prompt) con la
      pregunta ORIGINAL (no la reescrita), para que la respuesta suene
      natural respecto a lo que el usuario realmente escribio.

    Capa 1 (guardrails) SOLO se evalua en el PRIMER turno de la conversacion
    (sin conversation_history) -- ver hallazgo real abajo.

    Devuelve (ChatResponse, tiempo_ms) para poder loguear response_time_ms.
    """
    start = time.monotonic()

    # Small talk (saludos/agradecimientos/despedidas puros, ver
    # app.rag.guardrails.detect_smalltalk_response): hallazgo real de UX,
    # antes un "hola" caia en el mismo rechazo que una pregunta fuera de
    # tema (OUT_OF_SCOPE_MESSAGE). Se evalua ANTES de gastar un embedding,
    # y en CUALQUIER turno (no solo el primero, a diferencia de Capa 1 mas
    # abajo) -- un "gracias" al cierre de una conversacion legal legitima
    # debe reconocerse igual que un "hola" de apertura.
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

    query_embedding = embed_text(question)

    # Capa 1 de guardrails (LexChiapas_Guardrails.md, Fase 2.5): filtro barato
    # ANTES de gastar en reescritura/hybrid_search/generacion. Reusa el mismo
    # query_embedding que se necesita de todas formas para dense_search si no
    # hace falta reescribir, en vez de pedir uno nuevo.
    #
    # BUG REAL encontrado (transcript de usuario, 2026-07-30): esto antes
    # corria SIEMPRE sobre la pregunta cruda, incluso en seguimientos dentro
    # de una conversacion ya establecida como legal. El caso real: tras una
    # respuesta sobre limites de endeudamiento municipal, el seguimiento
    # "que ay de limites de endeudamiento" (sin la palabra "ley" ni similitud
    # suficiente a los 12 ejemplos fijos de dominio) se rechazo como fuera de
    # tema ANTES de que query rewriting (mas abajo) pudiera contextualizarlo
    # -- el fallback de keywords que el docstring viejo asumia "maneja
    # razonablemente bien" los seguimientos cortos NO cubria este caso real.
    # Si ya hay conversation_history, el primer turno de esa conversacion ya
    # paso Capa 1 -- no se vuelve a evaluar cada seguimiento aislado (mismo
    # criterio de costo/beneficio que ya aplica el modulo: el costo de un
    # falso positivo -- rechazar un seguimiento legal legitimo -- es mas alto
    # que dejar pasar una deriva de tema, que igual queda contenida por el
    # threshold real de retrieval mas abajo).
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

    # Cache semantico (Fase 3.7, ver app.rag.semantic_cache): SOLO para
    # preguntas SIN historial de conversacion. Una pregunta corta de
    # seguimiento ("Y las multas?") depende del contexto de ESA conversacion
    # en particular -- cachearla por similitud de embedding sola reutilizaria
    # la respuesta de un contexto distinto sin darse cuenta. Se usa el
    # query_embedding de la pregunta ORIGINAL (antes de query rewriting/
    # expansion de sinonimos legales) para que el lookup y el store despues
    # comparen sobre la misma base.
    original_query_embedding = query_embedding
    if not conversation_history:
        cached = cache_lookup(db, original_query_embedding)
        if cached is not None:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # search_time_ms/generation_time_ms del objeto cacheado reflejan
            # CUANDO SE GENERO originalmente, no este hit -- un cache hit no
            # busco ni genero nada de verdad (por eso es rapido). Sin este
            # reset se persistirian esos numeros viejos como si esta
            # respuesta hubiera tardado eso, contaminando avg/p95 de
            # /admin/metrics/performance con tiempos que no corresponden a
            # este request real.
            cached = cached.model_copy(update={"search_time_ms": None, "generation_time_ms": None})
            return cached, elapsed_ms

    search_start = time.monotonic()

    # Fase 6: reescribir SOLO si hace falta (pregunta corta + hay historial).
    # Si no se reescribio, se reusa el embedding ya calculado arriba para
    # Capa 1 -- no se gasta una llamada de embeddings de mas.
    search_question, was_rewritten = rewrite_query(question, conversation_history)

    # Fase 3.7 (hallazgo real del caso Art.1576, ver app.rag.legal_synonyms):
    # expansion determinista de sinonimos legales ANTES de embeber, para
    # consultas coloquiales que no comparten vocabulario con el articulo que
    # las responde (ej. "sin testamento" vs. el termino legal real "sucesion
    # legitima"). Se aplica sobre search_question (ya sea la original o la
    # reescrita por Fase 6) para que ambos mecanismos compongan.
    search_question, was_expanded = expand_legal_synonyms(search_question)

    if was_rewritten or was_expanded:
        query_embedding = embed_text(search_question)

    # Fase 6 (HyDE, ver app.rag.hyde y LexChiapas_Evolucion_RAG_Progresiva.md
    # seccion 1.2): un LLM barato genera una respuesta hipotetica a
    # search_question (ya reescrita/expandida arriba, para que HyDE tambien
    # se beneficie de esas dos correcciones) y se embebe ESA respuesta en
    # vez de la pregunta -- un fragmento de texto legal real se parece mas,
    # en el espacio de embeddings, a otro fragmento de texto legal (aunque
    # hipotetico) que a una pregunta coloquial de usuario. Reemplaza SOLO
    # query_embedding (dense_search); search_question sigue siendo el
    # query_text que se le pasa a hybrid_search para BM25/sparse_search sin
    # cambios -- mezclar el vocabulario generado por HyDE ahi diluiria la
    # precision lexica que BM25 necesita para matchear terminologia legal
    # exacta. Bandera config-driven (ai_config.json "hyde") para medir con/
    # sin sin tocar codigo; si la llamada al LLM falla,
    # generate_hypothetical_answer ya devuelve None y se sigue con el
    # embedding directo de search_question, igual que si esta feature no
    # existiera.
    if get_ai_config().get("hyde", {}).get("enabled", False):
        hypothetical_answer = generate_hypothetical_answer(search_question)
        if hypothetical_answer:
            query_embedding = embed_text(hypothetical_answer)

    candidates = hybrid_search(db, search_question, query_embedding)
    top_chunks = rerank(search_question, candidates)

    # search_time_ms (WEB_FRONTEND_PLAN.md Fase C.2, item 3.2): todo lo de
    # arriba desde search_start (query rewriting + sinonimos + HyDE +
    # hybrid_search + rerank) es "busqueda". Se corta ACA, antes de generar,
    # para no incluir la llamada al LLM principal en este numero.
    search_time_ms = int((time.monotonic() - search_start) * 1000)

    # Gate anti-alucinacion real: BM25 (sparse) no tiene un umbral absoluto
    # comparable al de dense (normaliza su mejor match a 1.0 sin importar que
    # tan irrelevante sea), asi que un chunk que SOLO vino de sparse nunca
    # puede por si solo justificar una respuesta "grounded". Si nada paso el
    # threshold real de dense_search, no se llama al LLM en absoluto.
    grounded = any(c.passed_threshold for c in top_chunks)
    generation_start = time.monotonic()
    answer, model_used, prompt_tokens, completion_tokens = generate_answer(
        question, top_chunks if grounded else [], conversation_history=conversation_history, technical=technical
    )
    # generation_time_ms: SOLO la llamada a generate_answer. Si no habia
    # chunks grounded, generate_answer devuelve NO_ENCONTRADO sin llamar al
    # LLM (ver app.rag.generator) -- el timer igual se calcula, va a dar un
    # numero chico real (nanosegundos de un return temprano), no None, para
    # no confundir "no llamo al LLM" con "no se midio".
    generation_time_ms = int((time.monotonic() - generation_start) * 1000)

    # Segundo gate de grounding (Fase 3.7, ver app.rag.grounding): si algo
    # cruzo el threshold real pero era lenguaje generico de otra ley, un
    # clasificador LLM barato juzga si la respuesta generada de verdad cubre
    # lo que se pregunto -- esto refleja ese juicio tambien en el flag
    # `grounded`. Solo puede degradar True a False, nunca al reves (si
    # grounded ya era False, no se llamo al LLM principal con chunks). Se
    # usa `question` (la pregunta ORIGINAL del usuario), no `search_question`
    # (que puede llevar terminos de expansion agregados solo para buscar).
    # Se le pasan los MISMOS top_chunks que uso el LLM principal -- le da al
    # clasificador algo concreto contra que comparar en vez de juzgar solo
    # por el tono del texto generado (hallazgo real: sin los chunks, dos
    # proveedores distintos discrepaban sobre el mismo texto).
    grounding_classifier_model = None
    if grounded:
        grounded, grounding_classifier_model = answer_is_grounded_in_practice(
            question, answer, top_chunks
        )

    elapsed_ms = int((time.monotonic() - start) * 1000)

    response = ChatResponse(
        answer=answer,
        retrieved_chunks=[
            RetrievedChunkSchema(
                chunk_id=c.chunk_id,
                document_nombre=c.document_nombre,
                articulo_numero=c.articulo_numero,
                similarity=c.similarity,
                content=c.content,
                passed_threshold=c.passed_threshold,
                derogado=is_articulo_derogado(c.content),
            )
            for c in top_chunks
        ],
        llm_model=model_used,
        grounded=grounded,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        grounding_classifier_model=grounding_classifier_model,
        was_rewritten=was_rewritten,
        search_time_ms=search_time_ms,
        generation_time_ms=generation_time_ms,
    )

    if not conversation_history:
        cache_store(db, question, original_query_embedding, response)

    return response, elapsed_ms
