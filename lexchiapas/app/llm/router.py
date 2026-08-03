from app.config import get_ai_config
from app.llm.providers import get_client_for_provider


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
    messages: list[dict], temperature: float | None = None
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
    """
    ai_config = get_ai_config()
    llm_config = ai_config["llm"]
    effective_temperature = temperature if temperature is not None else llm_config.get("temperature", 0.1)

    last_error: Exception | None = None
    for entry in llm_config["fallback_order"]:
        provider = entry["provider"]
        model = entry["model"]
        try:
            client = get_client_for_provider(provider)
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=effective_temperature,
                max_tokens=llm_config.get("max_tokens", 1024),
            )
            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else None
            completion_tokens = usage.completion_tokens if usage else None
            return response.choices[0].message.content, model, prompt_tokens, completion_tokens
        except Exception as exc:  # noqa: BLE001 - probamos la siguiente entrada
            last_error = exc
            continue

    raise AllModelsFailedError(
        f"todos los modelos de fallback_order fallaron: {last_error}"
    )
