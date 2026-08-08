import logging

from app.llm.router import AllModelsFailedError, generate_with_fallback
from app.rag.retriever import RetrievedChunk

logger = logging.getLogger("lexchiapas.grounding")

# Fase 3.7, hallazgo real (bucket B de la investigacion de causas raiz):
# dense_search puede pasar similarity_threshold=0.5 con chunks de OTRA ley
# por lenguaje legal generico ("delito"/"pena" en Codigo Fiscal para una
# pregunta sobre el Codigo Penal; "producto"/"control sanitario" en Ley de
# Salud para una pregunta de proteccion al consumidor) sin que esos chunks
# respondan la pregunta real -- el LLM principal, siguiendo REGLAS DE
# CONTENIDO en generator.SYSTEM_PROMPT, ya se niega o da un rodeo en el
# texto de la respuesta en esos casos, pero el flag `grounded` original
# solo mide si algo cruzo el threshold, no si el LLM realmente respondio.
#
# PRIMERA VERSION de este gate (descartada, ver PLAN.md Fase 3.7) usaba
# regex sobre las primeras frases de la respuesta -- descartada porque el
# fraseo real del LLM principal varia demasiado para que una lista de
# patrones tenga cobertura consistente.
#
# SEGUNDA VERSION (descartada tambien): un modelo barato unico via un solo
# proveedor -- descartada tras verificar en vivo una degradacion real de
# NVIDIA NIM ese dia (confirmada con el error explicito de la API). Se
# cambio a `generate_with_fallback` (multi-proveedor), y con eso se llego a
# la version que corrio en produccion 21/2/1 en el golden dataset.
#
# TERCERA VERSION (esta), dos mejoras reales pedidas por el usuario tras
# revisar la medicion de no-determinismo entre proveedores (ver PLAN.md):
# 1. El clasificador ahora recibe los CHUNKS REALES que pasaron el
#    threshold, no solo la respuesta final. Antes, la tarea era "¿esto
#    suena a que respondio?" -- un juicio abierto de estilo/tono donde cada
#    modelo trae su propio criterio no calibrado. Con los chunks, la tarea
#    se vuelve mecanica: "¿esta respuesta usa contenido de ESTOS pasajes, o
#    los ignora?" -- una comparacion de contenido, no una lectura de tono.
# 2. El prompt incluye 5 ejemplos fijos (few-shot) de casos YA verificados
#    a mano en esta sesion (consumidor, codigo_penal, sucesion, adopcion,
#    adulto_mayor), para anclar a todos los proveedores del fallback al
#    MISMO punto de referencia en vez de que cada uno traiga su propia
#    nocion de "fundamentado". A proposito NO se incluye proteccion_animal:
#    ese caso quedo documentado como genuinamente ambiguo (dos modelos en
#    desacuerdo legitimo) -- anclarlo con un veredicto fijo forzaria una
#    respuesta unica a algo que se decidio explicitamente no forzar.
#
# OJO: "grounded" aqui significa "tiene base real, no alucinada" -- NO
# significa "respondio TODO lo que se pregunto". Bug real encontrado antes
# de esta version: un criterio mas estricto ("responde de verdad lo que se
# pregunto") marco como NO grounded una respuesta legitima sobre sucesion
# (Art.1573 del Codigo Civil, MISMO tema/libro/capitulo que la pregunta,
# solo que incompleta) -- eso es una respuesta parcial honesta, no una
# alucinacion. El criterio correcto es MISMO TEMA vs. TEMA DISTINTO como
# consuelo, no completo vs. incompleto -- los ejemplos de abajo refuerzan
# justo esa distincion.
GROUNDING_CLASSIFIER_SYSTEM_PROMPT = (
    "Evaluas si una respuesta legal tiene fundamento real en los PASAJES "
    "LEGALES proporcionados -- es decir, si la respuesta usa contenido de "
    "esos pasajes especificos para cubrir el mismo tema/institucion "
    "juridica que el usuario pregunto, o si los pasajes son de un tema "
    "DISTINTO y la respuesta solo los ofrece como consuelo. No evalues si "
    "la respuesta es completa -- una respuesta parcial u honesta ('esto no "
    "especifica X') sobre el tema correcto SI cuenta como fundamentada. "
    "Responde SOLO con una palabra: SI o NO. Usa los ejemplos como "
    "referencia del criterio."
)

# 5 casos reales, verificados a mano contra el pipeline real de LexChiapas
# en esta sesion (ver PLAN.md Fase 3.7). Excerpts de los chunks reales
# recortados a lo esencial -- no hace falta el articulo completo para
# anclar el criterio, solo que el modelo vea la forma real del input.
_FEW_SHOT_EXAMPLES = [
    {
        "question": "Que dice la ley de proteccion al consumidor de Chiapas sobre las devoluciones de productos?",
        "chunks": [
            "[Ley de Salud del Estado de Chiapas, Articulo 213] obligaciones de lavanderias y tintorerias sobre entrega de prendas.",
            "[Codigo Civil para el Estado de Chiapas, Articulo 2266] mora del comprador en un contrato de compraventa.",
            "[Codigo Fiscal del Estado de Chiapas, Articulo 267] percepcion de productos del Estado.",
        ],
        "answer": "No puedo responder esa pregunta con los fragmentos legales proporcionados. Los textos disponibles tratan temas distintos: obligaciones de lavanderias, mora en compraventas, y percepcion de productos fiscales. Ninguno aborda devoluciones de productos al consumidor.",
        "verdict": "NO",
    },
    {
        "question": "Cual es la pena por el delito de robo segun el Codigo Penal de Chiapas?",
        "chunks": [
            "[Codigo Fiscal del Estado de Chiapas, Articulo 224] pena de tres meses a seis anos por apoderarse de mercancias en un recinto fiscal.",
            "[Codigo Fiscal del Estado de Chiapas, Articulo 214] el delito continuado puede aumentar la pena hasta una mitad mas.",
        ],
        "answer": "Los fragmentos proporcionados pertenecen al Codigo Fiscal, no al Codigo Penal. El articulo 224 se refiere especificamente al robo de mercancias en recintos fiscales, una figura distinta al delito de robo general tipificado en el Codigo Penal. No puedo responder con base en estos fragmentos.",
        "verdict": "NO",
    },
    {
        "question": "Quien hereda si una persona muere sin testamento en Chiapas?",
        "chunks": [
            "[Codigo Civil para el Estado de Chiapas, Articulo 1573] La herencia legitima se abre cuando no hay testamento o el que se otorgo es nulo o perdio su validez.",
        ],
        "answer": "Cuando una persona fallece sin testamento, se abre la herencia legitima (Articulo 1573 del Codigo Civil). Los fragmentos proporcionados no especifican el listado de personas con derecho a heredar en ese escenario.",
        "verdict": "SI",
    },
    {
        "question": "Quien puede adoptar a un menor en Chiapas y que requisitos necesita?",
        "chunks": [
            "[Codigo Civil para el Estado de Chiapas, Articulo 385] Los mayores de veinticinco anos, en pleno ejercicio de sus derechos, podran adoptar a menores, con una diferencia de al menos diecisiete anos de edad.",
        ],
        "answer": "El articulo 385 del Codigo Civil establece que las personas mayores de veinticinco anos que esten en pleno ejercicio de sus derechos pueden adoptar a menores, siempre que exista una diferencia de edad de al menos diecisiete anos.",
        "verdict": "SI",
    },
    {
        "question": "A partir de que edad se considera adulto mayor segun la ley de Chiapas?",
        "chunks": [
            "[Codigo de Atencion a la Familia y Grupos Vulnerables, Articulo 2 fraccion I] Adultos mayores: personas de sesenta anos o mas.",
        ],
        "answer": "Segun el Articulo 2, fraccion I, del Codigo de Atencion a la Familia y Grupos Vulnerables, se considera adulto mayor a la persona que cuenta con sesenta anos o mas de edad.",
        "verdict": "SI",
    },
]


def _format_chunks(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(sin pasajes)"
    return "\n\n".join(f"[{c.document_nombre}, Articulo {c.articulo_numero}]\n{c.content}" for c in chunks)


def _build_messages(question: str, answer_text: str, retrieved_chunks: list[RetrievedChunk]) -> list[dict]:
    messages = [{"role": "system", "content": GROUNDING_CLASSIFIER_SYSTEM_PROMPT}]
    for example in _FEW_SHOT_EXAMPLES:
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Pregunta del usuario: {example['question']}\n\n"
                    f"Pasajes legales recuperados:\n{chr(10).join(example['chunks'])}\n\n"
                    f"Respuesta generada: {example['answer']}"
                ),
            }
        )
        messages.append({"role": "assistant", "content": example["verdict"]})
    messages.append(
        {
            "role": "user",
            "content": (
                f"Pregunta del usuario: {question}\n\n"
                f"Pasajes legales recuperados:\n{_format_chunks(retrieved_chunks)}\n\n"
                f"Respuesta generada: {answer_text}"
            ),
        }
    )
    return messages


def answer_is_grounded_in_practice(
    question: str, answer_text: str, retrieved_chunks: list[RetrievedChunk] | None = None
) -> tuple[bool, str | None]:
    """Segundo gate de grounding, posterior a la generacion: solo puede
    DEGRADAR un `grounded=True` (calculado por el threshold real de
    dense_search) a False -- nunca al reves (ver
    rag_pipeline.answer_question). El gate original sigue siendo el unico
    responsable de decidir si se llama al LLM principal; este gate no
    cambia esa decision, solo corrige el flag `grounded` que se reporta
    cuando el LLM, con chunks reales en mano, en realidad no respondio lo
    que se pregunto.

    `retrieved_chunks`: los MISMOS chunks que se le dieron al LLM principal
    para generar `answer_text` (ver rag_pipeline.answer_question) -- le dan
    al clasificador algo concreto contra que comparar en vez de juzgar solo
    por el tono del texto generado.

    Devuelve (veredicto, proveedor_que_respondio) -- el proveedor se
    persiste en Message.grounding_classifier_model (ver
    app.bots.conversation_store) para poder diagnosticar despues si un
    desacuerdo real vino de un cambio de proveedor en el fallback, sin
    tener que re-investigar desde cero.

    Si TODOS los proveedores del fallback fallan (`AllModelsFailedError`),
    se asume `True` (no degradar) -- un componente auxiliar caido no debe
    convertir una respuesta ya generada en un falso "no encontrado", mismo
    principio de fallback silencioso que app.rag.query_rewriting.rewrite_query.
    """
    messages = _build_messages(question, answer_text, retrieved_chunks or [])
    try:
        verdict_raw, model_used, _, _ = generate_with_fallback(messages, temperature=0.0, fast=True)
        verdict = (verdict_raw or "").strip().upper()
        logger.info("grounding classifier (%s) verdict=%r para pregunta=%r", model_used, verdict, question)
        return verdict.startswith("SI"), model_used
    except AllModelsFailedError as exc:
        logger.warning("grounding classifier: todos los proveedores fallaron, se asume grounded=True: %s", exc)
        return True, None
    except Exception as exc:  # noqa: BLE001 - fallback silencioso, ver docstring
        logger.warning("grounding classifier fallo (error inesperado), se asume grounded=True: %s", exc)
        return True, None
