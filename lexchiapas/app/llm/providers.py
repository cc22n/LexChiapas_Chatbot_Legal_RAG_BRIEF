import logging
import time

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from app.config import get_ai_config, get_settings

logger = logging.getLogger("lexchiapas.llm.providers")

# Sin timeout explicito, el SDK de OpenAI puede colgarse mucho mas de lo
# razonable en una sola llamada lenta. Sin este timeout, app.llm.router.
# generate_with_fallback nunca pasa al siguiente modelo del fallback_order
# porque un cuelgue no es una excepcion -- el pipeline entero (y el bot en
# produccion) queda bloqueado indefinidamente en una sola respuesta lenta.
REQUEST_TIMEOUT_SECONDS = 60.0

# BUG REAL encontrado (2026-08-01, corrida de regresion post-ingesta de 12
# leyes nuevas): el SDK de OpenAI reintenta automaticamente 2 veces por
# default (max_retries=2, 3 intentos totales) ANTES de propagar la excepcion
# -- confirmado en vivo: una llamada a minimaxai/minimax-m3 que en teoria
# debia cortar a los 60s tardo 182.8s en fallar (casi exacto 3x
# REQUEST_TIMEOUT_SECONDS). Esto triplicaba el costo real de cada hop que
# fallara dentro de generate_with_fallback, que YA implementa su propio
# fallback entre proveedores -- dejar que el SDK reintente el MISMO proveedor
# que ya sabemos que fallo, antes de darle la oportunidad al siguiente de
# fallback_order, es trabajo redundante y exactamente lo que
# REQUEST_TIMEOUT_SECONDS intentaba evitar. max_retries=0 para que un timeout
# o error del proveedor actual pase inmediato al siguiente.
REQUEST_MAX_RETRIES = 0

# api_key por proveedor, todos los proveedores OpenAI-compatibles que se
# puedan agregar al fallback (ver ai_config.json llm.providers). Los
# embeddings SIEMPRE usan NVIDIA (NV-Embed) sin importar este mapeo -- la
# dimension del vector en pgvector ya esta fija a ese modelo (Fase 1), y no
# hay necesidad de multi-proveedor para embeddings como si la hay para
# generacion (fallback ante caidas/rate-limit del proveedor principal).
_PROVIDER_API_KEY_ATTR = {
    "nvidia_nim": "nvidia_api_key",
    "openai": "openai_api_key",
    "xai": "xai_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
}


def get_nim_client() -> OpenAI:
    return get_client_for_provider("nvidia_nim")


def get_client_for_provider(provider: str, timeout: float = REQUEST_TIMEOUT_SECONDS) -> OpenAI:
    """Cliente OpenAI-compatible para cualquier proveedor listado en
    ai_config.json llm.providers. NVIDIA NIM, OpenAI y xAI ya son
    OpenAI-compatibles de forma nativa; Gemini/Groq tambien exponen un
    endpoint OpenAI-compatible aunque no se usan en el fallback activo hoy
    (ver PLAN.md Fase 2.5/notas de proveedores para el porque).

    `timeout` (2026-08-06, auditoria de integracion LLM): por default usa
    REQUEST_TIMEOUT_SECONDS (60s), pero app.llm.router.generate_with_fallback
    puede pedir un timeout mas corto para tareas triviales (clasificacion de
    3 lineas, gate de grounding SI/NO) que hoy pagan el mismo timeout de 60s
    por hop que la generacion final -- ver "fast" ahi.
    """
    settings = get_settings()
    ai_config = get_ai_config()
    provider_config = ai_config["llm"]["providers"][provider]
    api_key_attr = _PROVIDER_API_KEY_ATTR[provider]
    api_key = getattr(settings, api_key_attr)
    return OpenAI(
        base_url=provider_config["base_url"],
        api_key=api_key,
        timeout=timeout,
        max_retries=REQUEST_MAX_RETRIES,
    )


# BUG REAL (2026-08-04, auditoria de integracion LLM): embed_text no tenia
# NINGUNA resiliencia -- a diferencia de app.llm.router.generate_with_fallback
# (que sobrevive un proveedor caido cayendo al siguiente de fallback_order),
# los embeddings SIEMPRE van a NVIDIA NIM sin alternativa (ver comentario de
# _PROVIDER_API_KEY_ATTR arriba, la dimension del vector en pgvector ya esta
# fija a NV-Embed). Con max_retries=0 (ver REQUEST_MAX_RETRIES arriba, puesto
# a proposito para el caso multi-proveedor), un solo 429/5xx/timeout
# transitorio de NVIDIA -- documentado como inestable en esta misma sesion --
# tumbaba el turno COMPLETO con el mensaje de error generico, en la PRIMERA
# llamada de cada turno (embed_text corre antes que classify_intent, antes
# de siquiera llegar a generate_with_fallback). Sin proveedor alterno al que
# caer, el unico mecanismo de resiliencia disponible es reintentar el MISMO
# proveedor unas pocas veces con backoff corto, solo para errores realmente
# transitorios (nunca para 400/401/404, que fallarian identico en un
# reintento).
_EMBED_MAX_ATTEMPTS = 3
_EMBED_RETRY_BACKOFF_SECONDS = (1.0, 2.0)
_EMBED_RETRYABLE_ERRORS = (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError)


def embed_text(text: str, input_type: str = "query") -> list[float]:
    """input_type: 'query' para preguntas del usuario, 'passage' para chunks
    que se van a indexar. NV-Embed es un modelo asimetrico: la API rechaza la
    llamada (400) si no se manda este parametro, y usar el valor equivocado
    en cada caso degrada la calidad del retrieval aunque la llamada no falle.

    "dimensions" (Migracion 2026-08-27, ver ai_config.json
    "_note_migracion_2026_08_27"): nvidia/llama-nemotron-embed-vl-1b-v2
    emite 2048 dims nativo, pero pgvector no soporta indices hnsw/ivfflat
    con mas de 2000 dims -- se trunca a ai_config["embeddings"]["dimension"]
    (1024, verificado con una llamada real que el modelo SI honra este
    parametro) para no tener que migrar el esquema de chunks.embedding.
    """
    ai_config = get_ai_config()
    client = get_nim_client()
    model = ai_config["embeddings"]["model"]
    dimension = ai_config["embeddings"]["dimension"]

    for attempt in range(1, _EMBED_MAX_ATTEMPTS + 1):
        try:
            response = client.embeddings.create(
                model=model,
                input=[text],
                extra_body={"input_type": input_type, "dimensions": dimension},
            )
            return response.data[0].embedding
        except _EMBED_RETRYABLE_ERRORS as exc:
            if attempt == _EMBED_MAX_ATTEMPTS:
                raise
            backoff = _EMBED_RETRY_BACKOFF_SECONDS[min(attempt - 1, len(_EMBED_RETRY_BACKOFF_SECONDS) - 1)]
            logger.warning(
                "embed_text: intento %d/%d fallo (%s: %s), reintentando en %.1fs",
                attempt, _EMBED_MAX_ATTEMPTS, type(exc).__name__, exc, backoff,
            )
            time.sleep(backoff)

    raise AssertionError("unreachable")  # el loop siempre retorna o re-lanza en el ultimo intento
