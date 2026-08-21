import json

from app.rag.claim_checker import ClaimCheck, check_claims
from app.rag.retriever import RetrievedChunk


def _fake_generate_with_fallback(response_text=None, exc=None):
    def _fake(messages, temperature=None, fast=False, response_format=None):
        if exc is not None:
            raise exc
        return response_text, "fake-model", None, None

    return _fake


def _chunk(document_nombre="Codigo Penal para el Estado de Chiapas", articulo="270", content="texto real"):
    return RetrievedChunk(
        chunk_id=1,
        document_nombre=document_nombre,
        articulo_numero=articulo,
        content=content,
        similarity=0.9,
        passed_threshold=True,
    )


def test_check_claims_parses_valid_json_response(monkeypatch):
    response = json.dumps(
        {
            "claims": [
                {"texto": "El robo se sanciona con prision", "respaldado": True, "fragmento": 1},
                {"texto": "La pena aumenta si es en casa habitada", "respaldado": False, "fragmento": None},
            ]
        }
    )
    monkeypatch.setattr(
        "app.rag.claim_checker.generate_with_fallback", _fake_generate_with_fallback(response_text=response)
    )

    result = check_claims("pregunta", "respuesta", [_chunk()])

    assert result == [
        ClaimCheck(texto="El robo se sanciona con prision", respaldado=True, fragmento_index=1),
        ClaimCheck(texto="La pena aumenta si es en casa habitada", respaldado=False, fragmento_index=None),
    ]


def test_check_claims_empty_list_when_no_material_claims(monkeypatch):
    response = json.dumps({"claims": []})
    monkeypatch.setattr(
        "app.rag.claim_checker.generate_with_fallback", _fake_generate_with_fallback(response_text=response)
    )

    result = check_claims("pregunta", "No encontre informacion sobre eso.", [])

    assert result == []


def test_check_claims_returns_none_on_invalid_json(monkeypatch):
    monkeypatch.setattr(
        "app.rag.claim_checker.generate_with_fallback",
        _fake_generate_with_fallback(response_text="esto no es JSON valido"),
    )

    result = check_claims("pregunta", "respuesta", [_chunk()])

    assert result is None


def test_check_claims_returns_none_when_all_providers_fail(monkeypatch):
    from app.llm.router import AllModelsFailedError

    monkeypatch.setattr(
        "app.rag.claim_checker.generate_with_fallback",
        _fake_generate_with_fallback(exc=AllModelsFailedError("todos fallaron")),
    )

    result = check_claims("pregunta", "respuesta", [_chunk()])

    assert result is None


def test_check_claims_sends_numbered_fragments_and_json_mode(monkeypatch):
    captured = {}

    def _fake(messages, temperature=None, fast=False, response_format=None):
        captured["messages"] = messages
        captured["temperature"] = temperature
        captured["fast"] = fast
        captured["response_format"] = response_format
        return json.dumps({"claims": []}), "fake-model", None, None

    monkeypatch.setattr("app.rag.claim_checker.generate_with_fallback", _fake)

    check_claims("pregunta", "respuesta", [_chunk(articulo="270"), _chunk(articulo="276")])

    user_content = captured["messages"][-1]["content"]
    assert "[1] Codigo Penal para el Estado de Chiapas, Articulo 270" in user_content
    assert "[2] Codigo Penal para el Estado de Chiapas, Articulo 276" in user_content
    assert captured["temperature"] == 0.0
    assert captured["fast"] is True
    assert captured["response_format"] == {"type": "json_object"}
