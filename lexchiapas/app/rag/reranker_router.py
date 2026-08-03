import logging

import httpx

from app.config import get_ai_config, get_settings

logger = logging.getLogger(__name__)


def _score_nvidia(query_text: str, passages: list[str], timeout: float) -> list[float]:
    config = get_ai_config()["reranking"]["providers"]["nvidia_nim"]
    settings = get_settings()
    response = httpx.post(
        config["url"],
        headers={"Authorization": f"Bearer {settings.nvidia_api_key}", "Accept": "application/json"},
        json={
            "model": config["model"],
            "query": {"text": query_text},
            "passages": [{"text": p} for p in passages],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    rankings = response.json()["rankings"]

    scores = [float("-inf")] * len(passages)
    for item in rankings:
        scores[item["index"]] = item["logit"]
    return scores


def _score_jina(query_text: str, passages: list[str], timeout: float) -> list[float]:
    config = get_ai_config()["reranking"]["providers"]["jina"]
    settings = get_settings()
    response = httpx.post(
        config["url"],
        headers={"Authorization": f"Bearer {settings.jina_api_key}", "Content-Type": "application/json"},
        json={"model": config["model"], "query": query_text, "documents": passages},
        timeout=timeout,
    )
    response.raise_for_status()
    results = response.json()["results"]

    scores = [float("-inf")] * len(passages)
    for item in results:
        scores[item["index"]] = item["relevance_score"]
    return scores


# Cada scorer devuelve una lista de floats alineada 1:1 con `passages` (mas
# alto = mas relevante). Las escalas NO son comparables entre proveedores
# (logit de NVIDIA vs relevance_score 0-1 de Jina) -- rerank() en
# app/rag/reranker.py solo usa los scores de UN proveedor a la vez (el
# primero que responda), nunca los mezcla.
_SCORERS = {"nvidia_nim": _score_nvidia, "jina": _score_jina}


def get_relevance_scores(query_text: str, passages: list[str]) -> tuple[list[float] | None, str]:
    """Intenta cada proveedor de `reranking.fallback_order` (ai_config.json)
    en orden, 1 intento por proveedor con timeout corto
    (`reranking.timeout_seconds` -- deliberadamente mas corto que el timeout
    de 60s del LLM en app/llm/providers.py REQUEST_TIMEOUT_SECONDS, porque
    el rerank es una llamada mas liviana y no debe repetir el mismo cuelgue
    largo que ya se arreglo ahi). Sin reintentos multiples por proveedor.

    Devuelve (scores, nombre_del_proveedor_usado). Si TODOS los proveedores
    fallan, devuelve (None, "none") -- el llamador (app/rag/reranker.py)
    debe caer a la heuristica local de solapamiento de palabras en ese caso,
    nunca dejar sin ranking a los candidatos.
    """
    if not passages:
        return [], "none"

    config = get_ai_config()["reranking"]
    timeout = config["timeout_seconds"]

    for provider in config["fallback_order"]:
        scorer = _SCORERS.get(provider)
        if scorer is None:
            logger.warning("proveedor de reranking desconocido en ai_config.json: %s", provider)
            continue
        try:
            scores = scorer(query_text, passages, timeout)
            return scores, provider
        except Exception:
            logger.warning("reranking con '%s' fallo, probando siguiente proveedor", provider, exc_info=True)
            continue

    return None, "none"
