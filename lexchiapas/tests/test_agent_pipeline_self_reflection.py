from langgraph.graph import END

from app.rag.agent_pipeline import _should_retry_after_generar

# Estos tests cubren solo la logica DETERMINISTICA del loop de self-reflection
# (Etapa 2, ver PLAN.md Fase 7 y app.rag.agent_pipeline._should_retry_after_
# generar) -- la condicion que decide si el grafo vuelve a "reformular" o
# termina en END, sin llamadas a la API de NVIDIA ni a la DB. Mismo criterio
# que tests/test_guardrails.py: la parte que SI depende de la red (el
# clasificador de grounding real, la reformulacion real via LLM) se midio
# manualmente contra el pipeline real -- ver PLAN.md Fase 7 Etapa 2 para esa
# evidencia.


def _state(**overrides):
    base = {
        "decision": "busqueda_general",
        "grounded_gate": True,
        "grounded": False,
        "intentos": 1,
        "max_intentos": 2,
    }
    base.update(overrides)
    return base


def test_retries_when_gate_was_true_but_second_gate_degraded():
    # El caso real que Etapa 2 existe para arreglar: dense_search SI paso el
    # threshold (grounded_gate=True), pero el segundo gate degrado a False.
    assert _should_retry_after_generar(_state()) == "reformular"


def test_does_not_retry_when_primary_gate_never_found_anything():
    # Medido en vivo esta sesion (ver docstring de _should_retry_after_generar):
    # reintentar aqui con busqueda_general reintroduciria falsos positivos que
    # busqueda_por_ley ya evita gratis para preguntas sobre leyes que no
    # existen en el corpus (consumidor, proteccion animal).
    assert _should_retry_after_generar(_state(grounded_gate=False)) == END


def test_does_not_retry_when_already_grounded():
    # Intento 1 ya tuvo exito -- no debe gastar una busqueda+generacion extra.
    assert _should_retry_after_generar(_state(grounded=True)) == END


def test_does_not_retry_past_max_intentos_hard_cap():
    # Tope duro: con max_intentos=2, despues del intento 2 (intentos=2) no se
    # reintenta sin importar el resto de las condiciones.
    assert _should_retry_after_generar(_state(intentos=2)) == END


def test_does_not_retry_articulo_especifico_route():
    # Invariante 3: no hay ambiguedad de fraseo que reformular resuelva en un
    # lookup exacto por clave (get_article) -- el articulo existe o no existe.
    assert (
        _should_retry_after_generar(_state(decision="articulo_especifico", grounded_gate=True))
        == END
    )


def test_does_not_retry_ninguna_route():
    assert _should_retry_after_generar(_state(decision="ninguna", grounded_gate=False)) == END


def test_retries_for_busqueda_por_ley_route_too():
    # El reintento aplica a AMBAS rutas de busqueda semantica, no solo
    # busqueda_general -- lo que nunca cambia entre intentos es la RUTA
    # (ver docstring), solo el texto de busqueda dentro de la misma ruta.
    assert _should_retry_after_generar(_state(decision="busqueda_por_ley")) == "reformular"
