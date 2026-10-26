import logging
import re
import time

from openai import RateLimitError

from app.config import get_ai_config
from app.llm.providers import REQUEST_TIMEOUT_SECONDS, get_client_for_provider
from app.llm.token_usage import record_usage

# ALT-01 (auditoria 2026-10-21): los 3 modelos de NVIDIA NIM comparten UNA
# cuenta/cuota, asi que un 429 en uno implica 429 en los otros dos; sin pausa
# la cascada caia en ~20 ms sobre OpenAI/xAI (creditos limitados de $5).
# Ante un 429 se espera un poco (respetando Retry-After, con tope) y se
# reintenta UNA vez el mismo modelo; si sigue en 429 se descartan los demas
# modelos de ESE proveedor en esta llamada.
RATE_LIMIT_DEFAULT_BACKOFF_SECONDS = 1.5
RATE_LIMIT_MAX_BACKOFF_SECONDS = 3.0


class AllModelsFailedError(Exception):
    pass


def _rate_limit_backoff_seconds(exc: RateLimitError) -> float:
    try:
        retry_after = float(exc.response.headers.get("retry-after", ""))
    except (AttributeError, TypeError, ValueError):
        return RATE_LIMIT_DEFAULT_BACKOFF_SECONDS
    return min(max(retry_after, 0.0), RATE_LIMIT_MAX_BACKOFF_SECONDS)


logger = logging.getLogger("lexchiapas.llm.router")

# Auditoria 2026-10-24: una respuesta con finish_reason == "length" se corto por
# el tope de tokens y llegaba al usuario cortada a mitad de frase (visto con
# minimax-m3.1-flash en la pregunta de jornada laboral); el router no revisaba
# finish_reason. Los modelos con razonamiento oculto (Kimi) consumen parte del
# tope pensando y pueden incluso devolver contenido vacio. Por eso, si se corta,
# se reintenta el MISMO modelo con llm.max_tokens_retry; si sigue cortado se
# pasa al siguiente; y solo si TODOS se cortan se devuelve el mejor texto
# recortado a la ultima frase completa (con aviso en el log).
DEFAULT_MAX_TOKENS_RETRY = 3072
# Abreviaturas juridicas que terminan en "." sin cerrar una frase ("Art. 22").
_ABBREVIATIONS = {"art", "arts", "fr", "fracc", "num", "núm", "no", "p", "pp", "inc", "cap", "sec", "lic", "dr", "sr", "sra"}


def _trim_to_last_sentence(text: str | None) -> str:
    """Recorta un texto cortado por el tope de tokens a su ultima frase
    completa. Si no hay ningun cierre de frase, lo devuelve sin cambios."""
    text = (text or "").rstrip()
    for match in reversed(list(re.finditer(r"[.!?](?=\s|$)", text))):
        previous_word = re.search(r"([A-Za-zÁÉÍÓÚáéíóúñÑ]+)$", text[: match.start()])
        if previous_word and previous_word.group(1).lower() in _ABBREVIATIONS:
            continue
        return text[: match.end()]
    return text


def _create_with_rate_limit_retry(client, create_kwargs, provider, rate_limited_providers):
    try:
        return client.chat.completions.create(**create_kwargs)
    except RateLimitError as rate_exc:
        time.sleep(_rate_limit_backoff_seconds(rate_exc))
        try:
            return client.chat.completions.create(**create_kwargs)
        except RateLimitError:
            rate_limited_providers.add(provider)
            raise


def get_primary_model() -> str:
    """Modelo de la primera entrada de fallback_order -- el que responde en
    condiciones normales. Cualquier mensaje con messages.llm_model distinto
    a este valor significa que ese fallback_order[0] fallo y otro proveedor
    respondio en su lugar (ver generate_with_fallback). No hace falta
    guardar un flag "fue fallback" por mensaje -- 100% derivable comparando
    llm_model contra este valor en el momento de la query (ver
    app.api.admin.metrics_performance)."""
    return get_ai_config()["llm"]["fallback_order"][0]["model"]


def generate_with_fallback(
    messages: list[dict],
    temperature: float | None = None,
    fast: bool = False,
    response_format: dict | None = None,
) -> tuple[str, str, int | None, int | None]:
    """Intenta cada entrada {provider, model} de fallback_order en orden.

    Devuelve (texto_respuesta, nombre_modelo_usado, prompt_tokens, completion_tokens).
    Los tokens vienen de response.usage (formato compatible con OpenAI); se
    devuelven None si la API no los reporta. El catalogo de cada proveedor
    cambia con poco aviso, por eso el orden vive en ai_config.json y no aqui.

    fallback_order mezcla proveedores (NVIDIA NIM primero, luego OpenAI/xAI
    como ultimo recurso -- ver PLAN.md Fase 2.5 y ai_config.json
    "_note_multiproveedor" para el porque de ese orden). Se pide un cliente
    nuevo por entrada (no uno solo reusado) porque cada entrada puede
    apuntar a un proveedor distinto, con su propia api_key/base_url.

    `temperature`: si se pasa, ANULA el valor de ai_config.json para esta
    llamada especifica -- usado por app.rag.grounding para forzar 0.0 en el
    clasificador de grounding (Fase 3.7, hallazgo real: el clasificador,
    reusando el temperature=0.1 de la generacion principal, daba veredictos
    distintos sobre el MISMO texto de entrada en llamadas repetidas -- 2/5
    False y 3/5 True en una prueba directa -- confirmando que el gate en si
    era no determinista en casos limite, no solo un reflejo de que el LLM
    principal genera texto distinto cada vez. Una tarea de clasificacion
    binaria SI/NO no necesita creatividad.

    `fast` (2026-08-06, auditoria de integracion LLM): usa
    ai_config.json "llm.fast_timeout_seconds" (default mas corto que
    REQUEST_TIMEOUT_SECONDS) en vez del timeout completo de 60s para CADA
    hop del fallback. Pensado para llamadas triviales que hoy pagan el mismo
    timeout que la generacion final aunque el output esperado sea de 1-3
    lineas (decidir, grounding, hyde, query rewriting, reformular): si el
    proveedor esta lento/caido, un timeout mas corto llega mas rapido al
    siguiente proveedor del fallback en vez de esperar 60s completos por
    hop. La generacion final (app.rag.generator.generate_answer) NO pasa
    fast=True a proposito -- esa si necesita el timeout completo, un
    corte prematuro ahi degradaria la respuesta real que ve el usuario.

    `response_format`: se pasa tal cual a client.chat.completions.create
    (ej. {"type": "json_object"}) -- usado por
    app.rag.agent_pipeline._node_decidir (ver LexChiapas_Plan_Futuro.md
    Parte C.1 para el experimento que confirmo 4/5 proveedores del
    fallback_order aceptandolo de forma confiable). Si un proveedor no
    soporta el parametro y lanza una excepcion, el loop de abajo ya lo trata
    igual que cualquier otro fallo de proveedor -- pasa al siguiente sin
    tratamiento especial.
    """
    ai_config = get_ai_config()
    llm_config = ai_config["llm"]
    effective_temperature = temperature if temperature is not None else llm_config.get("temperature", 0.1)
    timeout = llm_config.get("fast_timeout_seconds", REQUEST_TIMEOUT_SECONDS) if fast else REQUEST_TIMEOUT_SECONDS

    last_error: Exception | None = None
    truncated: tuple[str | None, str, int | None, int | None] | None = None
    rate_limited_providers: set[str] = set()
    for entry in llm_config["fallback_order"]:
        provider = entry["provider"]
        model = entry["model"]
        if provider in rate_limited_providers:
            continue
        try:
            client = get_client_for_provider(provider, timeout=timeout)
            create_kwargs = {
                "model": model,
                "messages": messages,
                # Override por entrada de fallback_order: hay modelos que solo
                # aceptan un valor (kimi-k2.6/k3 exigen temperature=1; otro
                # valor da HTTP 400 y el loop saltaria de proveedor sin avisar).
                "temperature": entry.get("temperature", effective_temperature),
            }
            if response_format is not None:
                create_kwargs["response_format"] = response_format
            # Presupuestos de tokens a probar: el base (por entrada o global) y,
            # si es mayor, el de reintento ante finish_reason == "length".
            base_max_tokens = entry.get("max_tokens", llm_config.get("max_tokens", 1024))
            retry_max_tokens = llm_config.get("max_tokens_retry", DEFAULT_MAX_TOKENS_RETRY)
            budgets = [base_max_tokens] + ([retry_max_tokens] if retry_max_tokens > base_max_tokens else [])
            for budget in budgets:
                create_kwargs["max_tokens"] = budget
                response = _create_with_rate_limit_retry(client, create_kwargs, provider, rate_limited_providers)
                usage = response.usage
                prompt_tokens = usage.prompt_tokens if usage else None
                completion_tokens = usage.completion_tokens if usage else None
                # Fase 9.8/A10: contabiliza los tokens de ESTA llamada en el
                # acumulador del turno (generacion vs auxiliar segun el scope). Es
                # el unico choke point de generacion, asi que capturar aca cubre
                # todas las llamadas sin tocar los call-sites auxiliares. Tambien
                # el intento cortado: esos tokens se pagaron.
                record_usage(prompt_tokens, completion_tokens)
                choice = response.choices[0]
                content = choice.message.content
                if getattr(choice, "finish_reason", None) != "length":
                    return content, model, prompt_tokens, completion_tokens
                logger.warning(
                    "router: %s/%s corto la respuesta por tope de tokens (max_tokens=%s, contenido=%d caracteres)",
                    provider, model, budget, len(content or ""),
                )
                if truncated is None or len(content or "") > len(truncated[0] or ""):
                    truncated = (content, model, prompt_tokens, completion_tokens)
            # Cortada con todos los presupuestos: probar el siguiente modelo.
        except Exception as exc:  # noqa: BLE001 - probamos la siguiente entrada
            last_error = exc
            continue

    if truncated is not None:
        # Ultimo recurso: ningun modelo dio una respuesta completa. Mejor una
        # respuesta recortada a su ultima frase completa que un error; queda en
        # el log para poder detectarlo.
        logger.error("router: TODOS los modelos cortaron la respuesta; se devuelve la mas larga recortada a su ultima frase")
        return _trim_to_last_sentence(truncated[0]), truncated[1], truncated[2], truncated[3]

    raise AllModelsFailedError(
        f"todos los modelos de fallback_order fallaron: {last_error}"
    )
