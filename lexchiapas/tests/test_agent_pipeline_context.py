from app.rag.agent_pipeline import _node_decidir, _parse_decision_json

# BUG REAL (2026-08-04, auditoria de integracion LLM): _node_decidir siempre
# vio la pregunta CRUDA del usuario, aunque answer_question_agentic ya
# resuelve referencias de contexto/typos via rewrite_query en `search_text`
# antes de invocar el grafo -- un seguimiento corto tipo "Y las multas?"
# llegaba sin contexto, y el LLM de "decidir" no tenia forma de saber a que
# ley se referia. Estos tests cubren SOLO la logica deterministica de que
# valor termina en el prompt (mockeando generate_with_fallback, sin llamar a
# la API real) -- el comportamiento real de rewrite_query en si ya tiene
# tests propios en tests/test_query_rewriting* y se verifico en vivo contra
# la API real esta sesion.
#
# Tambien cubre la migracion a JSON mode (2026-08-06, ver
# LexChiapas_Plan_Futuro.md Parte C.1): _node_decidir ahora pide
# response_format={"type":"json_object"} y fast=True, con _parse_decision
# (regex sobre texto plano) como red de seguridad si un proveedor ignora
# response_format.


def _fake_generate_with_fallback(captured_messages, captured_kwargs, response_text):
    def _fake(messages, temperature=None, fast=False, response_format=None):
        captured_messages.append(messages)
        captured_kwargs.append({"temperature": temperature, "fast": fast, "response_format": response_format})
        return response_text, "fake-model", None, None

    return _fake


def test_node_decidir_uses_search_text_when_available(monkeypatch):
    captured_messages: list[list[dict]] = []
    monkeypatch.setattr(
        "app.rag.agent_pipeline.generate_with_fallback",
        _fake_generate_with_fallback(captured_messages, [], '{"accion": "BUSQUEDA_GENERAL", "ley": null, "articulo": null}'),
    )

    state = {
        "question": "Y las multas?",
        "search_text": "Cuales son las multas o sanciones aplicables por tortura en Chiapas?",
    }
    _node_decidir(state)

    user_content = captured_messages[0][1]["content"]
    assert user_content == "Pregunta: Cuales son las multas o sanciones aplicables por tortura en Chiapas?"
    # La pregunta cruda original NUNCA debe llegar aca cuando hay search_text
    # resuelto -- eso era exactamente el bug.
    assert "Y las multas?" not in user_content


def test_node_decidir_falls_back_to_raw_question_without_search_text(monkeypatch):
    # Sin conversation_history, rewrite_query devuelve la pregunta sin
    # cambios (was_rewritten=False) y answer_question_agentic pone
    # search_text = question de todas formas -- pero _node_decidir en si debe
    # seguir funcionando aunque search_text no venga en el state (ej. si se
    # invoca el nodo directo, como en este test).
    captured_messages: list[list[dict]] = []
    monkeypatch.setattr(
        "app.rag.agent_pipeline.generate_with_fallback",
        _fake_generate_with_fallback(captured_messages, [], '{"accion": "BUSQUEDA_GENERAL", "ley": null, "articulo": null}'),
    )

    state = {"question": "Que dice la ley de aguas de Chiapas?"}
    _node_decidir(state)

    user_content = captured_messages[0][1]["content"]
    assert user_content == "Pregunta: Que dice la ley de aguas de Chiapas?"


def test_node_decidir_requests_json_mode_and_fast_timeout(monkeypatch):
    captured_messages: list[list[dict]] = []
    captured_kwargs: list[dict] = []
    monkeypatch.setattr(
        "app.rag.agent_pipeline.generate_with_fallback",
        _fake_generate_with_fallback(
            captured_messages, captured_kwargs, '{"accion": "NINGUNA", "ley": null, "articulo": null}'
        ),
    )

    _node_decidir({"question": "Gracias, eso era todo"})

    assert captured_kwargs[0]["fast"] is True
    assert captured_kwargs[0]["response_format"] == {"type": "json_object"}


def test_node_decidir_parses_valid_json_response(monkeypatch):
    monkeypatch.setattr(
        "app.rag.agent_pipeline.generate_with_fallback",
        _fake_generate_with_fallback(
            [], [], '{"accion": "ARTICULO_ESPECIFICO", "ley": "codigo penal", "articulo": "270"}'
        ),
    )

    result = _node_decidir({"question": "Que dice el articulo 270 del codigo penal de Chiapas?"})

    assert result == {"decision": "articulo_especifico", "law_name": "codigo penal", "articulo": "270"}


def test_node_decidir_falls_back_to_regex_when_provider_ignores_json_mode(monkeypatch):
    # Escenario real posible: el proveedor acepta response_format sin error
    # pero igual devuelve texto plano (o un proveedor del fallback que ni
    # siquiera soporta el parametro, y generate_with_fallback ya lo maneja
    # como cualquier otro fallo pasando al siguiente -- aca se simula el
    # caso donde SI hay respuesta pero no es JSON valido).
    monkeypatch.setattr(
        "app.rag.agent_pipeline.generate_with_fallback",
        _fake_generate_with_fallback(
            [], [], "ACCION: BUSQUEDA_POR_LEY\nLEY: ley de transparencia\nARTICULO: NINGUNA"
        ),
    )

    result = _node_decidir({"question": "Que dice la ley de transparencia de Chiapas?"})

    assert result == {"decision": "busqueda_por_ley", "law_name": "ley de transparencia", "articulo": None}


# ---------------------------------------------------------------------------
# _parse_decision_json
# ---------------------------------------------------------------------------


def test_parse_decision_json_valid():
    raw = '{"accion": "BUSQUEDA_GENERAL", "ley": null, "articulo": null}'
    assert _parse_decision_json(raw) == ("busqueda_general", None, None)


def test_parse_decision_json_with_ley_and_articulo():
    raw = '{"accion": "ARTICULO_ESPECIFICO", "ley": "codigo civil", "articulo": "15 Bis"}'
    assert _parse_decision_json(raw) == ("articulo_especifico", "codigo civil", "15 Bis")


def test_parse_decision_json_invalid_json_returns_none():
    assert _parse_decision_json("esto no es JSON") is None
    assert _parse_decision_json("") is None


def test_parse_decision_json_non_dict_returns_none():
    assert _parse_decision_json("[1, 2, 3]") is None
    assert _parse_decision_json('"solo un string"') is None


def test_parse_decision_json_invalid_accion_returns_none():
    raw = '{"accion": "ALGO_INVENTADO", "ley": null, "articulo": null}'
    assert _parse_decision_json(raw) is None


def test_parse_decision_json_downgrades_busqueda_por_ley_without_ley():
    raw = '{"accion": "BUSQUEDA_POR_LEY", "ley": null, "articulo": null}'
    assert _parse_decision_json(raw) == ("busqueda_general", None, None)
