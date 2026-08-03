import logging

from app.llm.router import AllModelsFailedError, generate_with_fallback

logger = logging.getLogger("lexchiapas.query_rewriting")

# Fase 6 (LexChiapas_Evolucion_RAG_Progresiva.md, seccion 1.1): un LLM
# barato reescribe preguntas de seguimiento coloquiales a consultas legales
# auto-contenidas ANTES de embeber/buscar. Cierra el gap real encontrado en
# Fase 2.6: la memoria conversacional alimenta el PROMPT de generacion, pero
# hybrid_search seguia operando solo sobre la pregunta cruda -- una pregunta
# corta como "Y que sanciones tiene?" no genera un embedding lo bastante
# cercano a los articulos reales aunque el tema ya se hubiera hablado antes.
#
# BUG REAL encontrado (2026-07-30): este modulo originalmente usaba un
# cliente/modelo FIJO (mistralai/ministral-14b-instruct-2512, elegido en
# Fase 6 tras probar 2 alternativas), a diferencia de HyDE/grounding/el nodo
# "decidir" del agente, que ya usaban generate_with_fallback. Ese modelo
# llego a su fin de vida en el catalogo de NVIDIA NIM el 2026-07-27 y dejo
# de existir -- rewrite_query cayo en su fallback silencioso (pregunta sin
# cambios) en el 100% de las llamadas desde entonces, sin ningun error
# visible (el fallback esta disenado para no bloquear el pipeline). Se migra
# a generate_with_fallback para converger con el mismo patron de resiliencia
# multi-proveedor que ya usa el resto del pipeline -- el catalogo de NVIDIA
# cambia con poco aviso, ningun componente deberia depender de un solo slug
# de modelo fijo (ver PLAN.md Fase 2.5 y ai_config.json "llm.fallback_order").

REWRITE_SYSTEM_PROMPT = (
    "Reescribes preguntas legales en espanol para busqueda: corriges "
    "errores de tipeo, ortografia y lenguaje coloquial a terminologia "
    "legal formal, y si hay contexto de un turno anterior, ademas "
    "resuelves referencias ambiguas (pronombres, \"y eso?\", etc). "
    "Preservas el sentido original -- NUNCA agregas hechos, leyes, ni "
    "datos que el usuario no menciono. Responde SOLO con la pregunta "
    "reescrita, en una sola linea, sin explicaciones, sin comillas, sin "
    "formato markdown.\n\n"
    "Ejemplo 1 (normalizar tipeo/registro coloquial, sin contexto previo):\n"
    "Pregunta: que pasa si talas un arbol. quiero saber si es permitido, "
    "si bajo circunstancias\n"
    "Reescrita: Es legal talar un arbol en Chiapas? Bajo que circunstancias esta permitido?\n\n"
    "Ejemplo 2 (resolver referencia usando el contexto de un turno anterior):\n"
    "Contexto: El usuario pregunto sobre tortura segun la ley de Chiapas.\n"
    "Seguimiento: Y las multas?\n"
    "Reescrita: Que sanciones o multas contempla la ley de tortura de Chiapas?"
)

# Umbral de palabras para decidir si una pregunta CON historial vale la pena
# reescribir. Heuristica barata (sin API): una pregunta larga con historial
# casi siempre ya es auto-contenida (trae su propio tema); una corta con
# pronombres sueltos ("Y las multas?", "Y eso aplica igual?") es la que
# depende de contexto previo.
SHORT_QUESTION_WORD_THRESHOLD = 6


def needs_rewriting(question: str, conversation_history: list[dict] | None) -> bool:
    """Reescribe si es el PRIMER turno (normaliza tipeo/registro coloquial,
    sin nada que contextualizar -- ver REWRITE_SYSTEM_PROMPT Ejemplo 1) o si
    es una pregunta corta CON historial (resuelve referencias, Ejemplo 2).

    Hallazgo real (transcript de usuario, 2026-07-30): el primer mensaje de
    una conversacion nueva, largo pero lleno de errores de tipeo
    ("quirso saber si espermidos, si bajo circustancias"), nunca pasaba por
    aca porque el gate original exigia historial -- el registro coloquial
    llegaba intacto a embeddings/hybrid_search. Preguntas largas CON
    historial (ya se establecio el tema, no necesitan reescritura) siguen
    usando el umbral de palabras para no gastar la llamada de mas."""
    if not conversation_history:
        return True
    return len(question.split()) <= SHORT_QUESTION_WORD_THRESHOLD


def _last_user_context(conversation_history: list[dict]) -> str:
    """Usa el ultimo turno de USUARIO (no la respuesta del bot) como
    contexto -- normalmente basta el turno inmediato anterior para resolver
    una referencia como "y las multas?" o "y eso aplica igual?". No hace
    falta mandar toda la ventana de 8 mensajes solo para reescribir.
    """
    last_user_turns = [m["content"] for m in conversation_history if m.get("role") == "user"]
    return last_user_turns[-1] if last_user_turns else ""


def rewrite_query(question: str, conversation_history: list[dict] | None = None) -> tuple[str, bool]:
    """Devuelve (pregunta_para_buscar, se_reescribio).

    Si no hace falta reescribir, o la llamada al LLM barato falla por
    cualquier motivo, devuelve la pregunta ORIGINAL sin cambios -- la
    reescritura es una optimizacion de retrieval, nunca debe bloquear el
    pipeline principal si el modelo de reescritura falla o esta lento
    (mismo principio que el timeout de 60s en app/llm/providers.py: un
    componente auxiliar lento no debe tumbar todo el flujo).
    """
    if not needs_rewriting(question, conversation_history):
        return question, False

    context = _last_user_context(conversation_history) if conversation_history else ""
    if conversation_history and not context:
        # Hay historial pero ningun turno de usuario previo (caso raro) --
        # no hay contexto real que resolver, no vale la pena reescribir.
        return question, False

    user_content = (
        f"Contexto: {context}\nSeguimiento: {question}\nReescrita:"
        if context
        else f"Pregunta: {question}\nReescrita:"
    )

    messages = [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        rewritten, model_used, _, _ = generate_with_fallback(messages, temperature=0.1)
        rewritten = (rewritten or "").strip()
        if not rewritten:
            return question, False
        logger.info("query rewriting (%s): %r -> %r", model_used, question, rewritten)
        return rewritten, True
    except AllModelsFailedError as exc:
        logger.warning("query rewriting: todos los proveedores fallaron, usando pregunta original: %s", exc)
        return question, False
    except Exception as exc:  # noqa: BLE001 - fallback silencioso a la pregunta original
        logger.warning("query rewriting fallo (error inesperado), usando pregunta original: %s", exc)
        return question, False
