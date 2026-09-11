from app.config import get_ai_config
from app.llm.providers import REQUEST_TIMEOUT_SECONDS, get_client_for_provider
from app.llm.token_usage import record_usage


class AllModelsFailedError(Exception):
    pass


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
    for entry in llm_config["fallback_order"]:
        provider = entry["provider"]
        model = entry["model"]
        try:
            client = get_client_for_provider(provider, timeout=timeout)
            create_kwargs = {
                "model": model,
                "messages": messages,
                "temperature": effective_temperature,
                "max_tokens": llm_config.get("max_tokens", 1024),
            }
            if response_format is not None:
                create_kwargs["response_format"] = response_format
            response = client.chat.completions.create(**create_kwargs)
            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else None
            completion_tokens = usage.completion_tokens if usage else None
            # Fase 9.8/A10: contabiliza los tokens de ESTA llamada en el
            # acumulador del turno (generacion vs auxiliar segun el scope). Es
            # el unico choke point de generacion, asi que capturar aca cubre
            # todas las llamadas sin tocar los call-sites auxiliares.
            record_usage(prompt_tokens, completion_tokens)
            return response.choices[0].message.content, model, prompt_tokens, completion_tokens
        except Exception as exc:  # noqa: BLE001 - probamos la siguiente entrada
            last_error = exc
            continue

    raise AllModelsFailedError(
        f"todos los modelos de fallback_order fallaron: {last_error}"
    )
