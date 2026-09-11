"""Paridad entre los dos pipelines RAG (Fase 9.8/C6).

LexChiapas tiene DOS pipelines intercambiables via ai_config.json
"agentic_rag.enabled": el lineal (app.rag.rag_pipeline.answer_question) y el
agentico (app.rag.agent_pipeline.answer_question_agentic). Una optimizacion
agregada a uno y NO al otro queda MUERTA en produccion cuando el flag apunta
al pipeline que no la tiene -- ya paso dos veces:

  - rewrite_query (2026-08-04): existia en el lineal desde la Fase 6 pero
    nunca se habia portado al agente; con agentic_rag.enabled=true en
    produccion, cada seguimiento corto se degradaba.
  - cache semantico + expansion de sinonimos (hallazgo C6 de la auditoria
    2026-09-09): enabled=true en config pero JAMAS invocados por el pipeline
    agentico -- codigo muerto en la ruta real durante semanas.

Este test es un guard ESTRUCTURAL barato (sin API real, sin DB): exige que
ambos pipelines importen Y llamen las mismas optimizaciones de retrieval. No
prueba que se comporten identico (eso es tests/test_rag_regression.py contra
el golden dataset), solo que ninguna de las dos rutas pierda una optimizacion
que la otra tiene. Si a futuro se agrega una optimizacion nueva a una sola
ruta a proposito, este test obliga a documentarlo aqui explicitamente en vez
de que la divergencia pase inadvertida.
"""

import inspect

import pytest

import app.rag.agent_pipeline as agent_pipeline
import app.rag.rag_pipeline as rag_pipeline

# Optimizaciones de retrieval que DEBEN estar en ambos pipelines. HyDE NO
# esta aca a proposito: esta desactivado (ai_config.json "hyde.enabled" =
# false, medido que empeora retrieval con el modelo de embeddings actual) y
# solo el pipeline lineal lo invoca condicionalmente -- si se reactiva algun
# dia, portarlo al agente y agregarlo a esta lista.
SHARED_OPTIMIZATIONS = ("cache_lookup", "cache_store", "expand_legal_synonyms")

PIPELINE_MODULES = (
    ("rag_pipeline", rag_pipeline),
    ("agent_pipeline", agent_pipeline),
)


@pytest.mark.parametrize("module_name,module", PIPELINE_MODULES)
@pytest.mark.parametrize("optimization", SHARED_OPTIMIZATIONS)
def test_both_pipelines_import_and_call_optimization(module_name, module, optimization):
    assert hasattr(module, optimization), (
        f"{module_name} no importa {optimization!r} -- optimizacion de "
        f"retrieval ausente en esta ruta (ver docstring: bug de codigo muerto)"
    )
    source = inspect.getsource(module)
    assert f"{optimization}(" in source, (
        f"{module_name} importa {optimization!r} pero nunca lo llama -- "
        f"import muerto, la optimizacion no corre en esta ruta"
    )
