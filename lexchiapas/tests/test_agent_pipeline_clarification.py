import pytest

from app.rag.agent_pipeline import _node_generar

# Fase 9.3 (coverage checker -- pedir aclaracion en vez de responder o
# admitir "no encontre informacion"): estos tests cubren SOLO la logica
# deterministica de _node_generar cuando AgentState.clarification_options
# esta poblado (ver _node_buscar/get_article_ambiguity para donde se llena
# ese campo en un caso real). No llaman a la API real -- si el codigo
# llegara a invocar generate_answer por error en este camino, el
# monkeypatch de abajo lo hace fallar de forma ruidosa en vez de colgarse
# esperando una respuesta de red real.


def _explode_if_called(*args, **kwargs):
    raise AssertionError("generate_answer no deberia llamarse cuando hay clarification_options")


def test_node_generar_returns_clarification_without_calling_llm(monkeypatch):
    monkeypatch.setattr("app.rag.agent_pipeline.generate_answer", _explode_if_called)

    state = {
        "question": "que dice el articulo 5 del codigo civil",
        "decision": "articulo_especifico",
        "chunks": [],
        "clarification_options": [
            "Codigo Civil para el Estado de Chiapas - Libro Primero (De las Personas)",
            "Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)",
        ],
    }

    result = _node_generar(state)

    assert "Libro Primero" in result["answer"]
    assert "Libro Segundo" in result["answer"]
    assert result["grounded"] is False
    assert result["grounded_gate"] is False
    assert result["model_used"] is None
    assert result["prompt_tokens"] is None
    assert result["completion_tokens"] is None
    assert result["grounding_classifier_model"] is None


def test_node_generar_ignores_empty_clarification_options(monkeypatch):
    # Lista vacia (el caso normal, sin ambiguedad) no debe activar el
    # camino de aclaracion -- debe seguir el flujo normal de
    # articulo_especifico (chunks vacios -> grounded_gate False -> llama a
    # generate_answer igual que siempre, ver docstring de _node_generar).
    called = {}

    def _fake_generate_answer(question, chunks, conversation_history=None, technical=False):
        called["invoked"] = True
        return "No encontre informacion sobre eso.", None, None, None

    monkeypatch.setattr("app.rag.agent_pipeline.generate_answer", _fake_generate_answer)

    state = {
        "question": "que dice el articulo 999 de una ley que no existe",
        "decision": "articulo_especifico",
        "chunks": [],
        "clarification_options": [],
    }

    result = _node_generar(state)

    assert called.get("invoked") is True
    assert result["grounded"] is False
