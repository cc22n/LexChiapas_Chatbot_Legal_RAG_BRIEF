import logging

from app.llm.router import AllModelsFailedError, generate_with_fallback

logger = logging.getLogger("lexchiapas.hyde")

# Fase 6 (LexChiapas_Evolucion_RAG_Progresiva.md, seccion 1.2): HyDE
# (Hypothetical Document Embeddings). En vez de embeber la pregunta cruda del
# usuario para dense_search, un LLM barato genera primero una respuesta
# hipotetica (aunque imperfecta o inventada) a la pregunta -- la intuicion es
# que un fragmento de texto legal real (un articulo de ley) se parece mas,
# en el espacio de embeddings, a OTRO fragmento de texto legal (aunque
# hipotetico) que a una pregunta coloquial de usuario. El texto generado
# aqui NUNCA se muestra al usuario ni se usa para BM25 (ver
# rag_pipeline.answer_question) -- es exclusivamente un vehiculo para
# mejorar el embedding de busqueda dense.
#
# Se reusa generate_with_fallback (app.llm.router) en vez de un cliente fijo
# a un solo proveedor/modelo (a diferencia de app.rag.query_rewriting, que
# usa un modelo fijo): el mismo criterio de resiliencia multi-proveedor que
# ya aplica al resto del pipeline (generacion principal, clasificador de
# grounding) -- el catalogo de NVIDIA NIM cambia y esta llamada no deberia
# quedar atada a un slug de modelo que puede desaparecer.
HYDE_SYSTEM_PROMPT = (
    "Escribes un fragmento breve (2 a 4 oraciones) de texto legal, en el "
    "registro de una ley o codigo del Estado de Chiapas, que PARECERIA la "
    "respuesta correcta a la pregunta del usuario. No necesita ser verdadero "
    "ni verificado -- es solo un texto de referencia para mejorar una "
    "busqueda semantica, nunca se muestra al usuario. Responde SOLO con el "
    "fragmento, sin explicaciones, sin comillas, sin formato markdown, en "
    "espanol."
)


def generate_hypothetical_answer(question: str) -> str | None:
    """Devuelve un fragmento de texto legal hipotetico para `question`, o
    None si la llamada falla por cualquier motivo.

    Fallback seguro (mismo principio que app.rag.query_rewriting.
    rewrite_query): HyDE es una optimizacion de retrieval, nunca debe
    bloquear el pipeline principal. Si esto devuelve None, el llamador debe
    seguir con el embedding directo de la pregunta, igual que si HyDE no
    existiera.
    """
    messages = [
        {"role": "system", "content": HYDE_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        text, model_used, _, _ = generate_with_fallback(messages, temperature=0.3)
        text = (text or "").strip()
        if not text:
            return None
        logger.info("hyde (%s): %r -> %r", model_used, question, text)
        return text
    except AllModelsFailedError as exc:
        logger.warning("hyde: todos los proveedores fallaron, usando embedding directo: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - fallback silencioso, ver docstring
        logger.warning("hyde fallo (error inesperado), usando embedding directo: %s", exc)
        return None
