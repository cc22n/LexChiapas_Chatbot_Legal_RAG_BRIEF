from app.rag.query_rewriting import (
    CLARIFICATION_QUESTION_MARKER,
    SHORT_QUESTION_WORD_THRESHOLD,
    _last_turn_is_clarification_question,
    needs_rewriting,
    rewrite_query,
)

# BUG REAL encontrado probando el agente en produccion (Fase 9.5): cuando el
# usuario responde a la pregunta de aclaracion de la Fase 9.3 (ver
# app.rag.agent_pipeline._node_generar) con SOLO el nombre oficial de la ley
# (ej. "Codigo Penal para el Estado de Chiapas", 7 palabras), el umbral de
# SHORT_QUESTION_WORD_THRESHOLD (6 palabras) lo clasificaba como pregunta
# "larga" y needs_rewriting devolvia False -- el numero de articulo del
# turno anterior se perdia, y el nodo "decidir" volvia a BUSQUEDA_POR_LEY en
# vez de retomar ARTICULO_ESPECIFICO. Estos tests cubren la logica
# deterministica que fuerza la reescritura en ese caso especifico.


def test_needs_rewriting_true_without_history():
    assert needs_rewriting("cualquier pregunta larga que se te ocurra aca", None) is True


def test_needs_rewriting_true_for_short_followup():
    history = [{"role": "user", "content": "Que dice la ley de tortura de Chiapas?"}]
    assert needs_rewriting("Y las multas?", history) is True


def test_needs_rewriting_false_for_long_followup_without_clarification():
    history = [
        {"role": "user", "content": "Que dice la ley de tortura de Chiapas?"},
        {"role": "assistant", "content": "La ley establece sanciones de X a Y anos de prision."},
    ]
    long_question = "Y que pasa si la victima es un menor de edad en ese mismo caso"
    assert len(long_question.split()) > SHORT_QUESTION_WORD_THRESHOLD
    assert needs_rewriting(long_question, history) is False


def test_needs_rewriting_true_after_clarification_question_even_if_long():
    # El caso real: "Codigo Penal para el Estado de Chiapas" tiene 7
    # palabras (> SHORT_QUESTION_WORD_THRESHOLD=6), pero como el turno
    # anterior fue la aclaracion de la Fase 9.3, igual debe reescribirse.
    history = [
        {"role": "user", "content": "Que dice el articulo 270 del codigo penal?"},
        {
            "role": "assistant",
            "content": (
                f"{CLARIFICATION_QUESTION_MARKER}: Codigo Penal para el Estado de Chiapas; "
                "Codigo de Procedimientos Penales para el Estado de Chiapas. "
                "Podrias decirme cual de estas es la que te interesa?"
            ),
        },
    ]
    followup = "Codigo Penal para el Estado de Chiapas"
    assert len(followup.split()) > SHORT_QUESTION_WORD_THRESHOLD
    assert needs_rewriting(followup, history) is True


def test_last_turn_is_clarification_question_false_for_normal_assistant_answer():
    history = [
        {"role": "user", "content": "Que dice la ley de tortura de Chiapas?"},
        {"role": "assistant", "content": "La ley establece sanciones de X a Y anos de prision."},
    ]
    assert _last_turn_is_clarification_question(history) is False


def test_last_turn_is_clarification_question_false_without_history():
    assert _last_turn_is_clarification_question(None) is False
    assert _last_turn_is_clarification_question([]) is False


def test_last_turn_is_clarification_question_false_when_last_turn_is_user():
    # Caso raro (no deberia pasar en produccion, los turnos alternan), pero
    # la funcion no debe reventar ni dar falso positivo si el ultimo turno
    # es del usuario en vez del asistente.
    history = [{"role": "user", "content": f"{CLARIFICATION_QUESTION_MARKER}: X; Y."}]
    assert _last_turn_is_clarification_question(history) is False


def test_rewrite_query_merges_articulo_from_context_after_clarification(monkeypatch):
    # Confirma que rewrite_query en si (no solo needs_rewriting) toma el
    # contexto del ULTIMO TURNO DE USUARIO (que trae el articulo original),
    # no el turno del asistente que esta justo antes en la conversacion.
    captured = {}

    def _fake_generate_with_fallback(messages, temperature=None, fast=False, response_format=None):
        captured["messages"] = messages
        return (
            "Que dice el articulo 270 del Codigo Penal para el Estado de Chiapas?",
            "fake-model",
            None,
            None,
        )

    monkeypatch.setattr("app.rag.query_rewriting.generate_with_fallback", _fake_generate_with_fallback)

    history = [
        {"role": "user", "content": "Que dice el articulo 270 del codigo penal?"},
        {
            "role": "assistant",
            "content": f"{CLARIFICATION_QUESTION_MARKER}: Codigo Penal; Codigo de Procedimientos Penales.",
        },
    ]
    rewritten, was_rewritten = rewrite_query("Codigo Penal para el Estado de Chiapas", history)

    assert was_rewritten is True
    assert rewritten == "Que dice el articulo 270 del Codigo Penal para el Estado de Chiapas?"
    user_content = captured["messages"][1]["content"]
    assert "Contexto: Que dice el articulo 270 del codigo penal?" in user_content
    assert "Seguimiento: Codigo Penal para el Estado de Chiapas" in user_content
