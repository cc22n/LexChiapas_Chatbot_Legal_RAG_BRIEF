"""Modo investigacion (app.rag.research): sin red ni base de datos (LLM, busqueda y reranker simulados)."""

import json

import pytest

from app.rag import research
from app.rag.guardrails import OUT_OF_SCOPE_MESSAGE
from app.rag.retriever import RetrievedChunk


def _chunk(chunk_id, doc, art, passed=True, sim=0.8):
    return RetrievedChunk(chunk_id=chunk_id, document_nombre=doc, articulo_numero=art,
                          content=f"Articulo {art}. Texto de prueba.", similarity=sim, passed_threshold=passed)


# ---------------------------------------------------------------- parse_plan
def test_parse_plan_reads_subquestions_and_areas():
    raw = json.dumps({"subpreguntas": ["Quien debe pagar?", "Que plazo hay?"], "areas": ["Fiscal", " civil "]})
    assert research.parse_plan(raw, "pregunta original", 3) == (["Quien debe pagar?", "Que plazo hay?"], ["fiscal", "civil"])


def test_parse_plan_tolerates_code_fences_and_caps_and_dedupes():
    raw = "```json\n" + json.dumps({"subpreguntas": ["a1", "a1", "Pregunta Original", "a2", "a3", "a4"], "areas": []}) + "\n```"
    subs, _ = research.parse_plan(raw, "pregunta original", 3)
    assert subs == ["a1", "a2", "a3"]  # sin repetidos, sin la pregunta original, con tope


@pytest.mark.parametrize("raw", [None, "", "no es json", "[1, 2]", json.dumps({"subpreguntas": "texto"}), json.dumps({"subpreguntas": [1, None]})])
def test_parse_plan_bad_input_returns_empty(raw):
    assert research.parse_plan(raw, "q", 3)[0] == []


# ------------------------------------------------------------ merge_candidates
def test_merge_candidates_dedupes_keeping_best_similarity_and_threshold():
    a = [_chunk(1, "Ley A", "1", passed=False, sim=0.4), _chunk(2, "Ley A", "2")]
    b = [_chunk(1, "Ley A", "1", passed=True, sim=0.7), _chunk(3, "Ley B", "9")]
    merged = {c.chunk_id: c for c in research.merge_candidates([a, b])}
    assert sorted(merged) == [1, 2, 3]
    assert merged[1].similarity == 0.7 and merged[1].passed_threshold is True


# ------------------------------------------------------------------ pipeline
@pytest.fixture()
def pipeline(monkeypatch):
    """Parcha todas las dependencias externas y devuelve un registro de llamadas."""
    calls = {"plan": 0, "search": [], "rerank": [], "generate": [], "gate": 0}
    monkeypatch.setattr(research, "get_ai_config", lambda: {"agentic_rag": {"research": {"enabled": True, "max_subquestions": 3, "max_llm_calls": 4, "top_k": 8}}})
    monkeypatch.setattr(research, "embed_text", lambda text: [0.1, 0.2])
    monkeypatch.setattr(research, "detect_smalltalk_response", lambda q: None)
    monkeypatch.setattr(research, "classify_intent", lambda q, question_embedding=None: (True, 0.9))
    monkeypatch.setattr(research, "expand_legal_synonyms", lambda q: (q, False))
    monkeypatch.setattr(research, "release_connection", lambda db: None)
    monkeypatch.setattr(research, "get_articulos_historial_bulk", lambda db, pairs: {})

    def fake_plan(messages, temperature=None, fast=False, response_format=None):
        calls["plan"] += 1
        return json.dumps({"subpreguntas": ["quien debe pagar", "que plazo hay"], "areas": ["fiscal"]}), "modelo-plan", 10, 5

    def fake_search(db, text, embedding, document_filter=None):
        calls["search"].append(text)
        return [_chunk(len(calls["search"]), "Codigo Fiscal", str(len(calls["search"])))]

    def fake_rerank(query, candidates, top_k=None):
        calls["rerank"].append((query, len(candidates), top_k))
        return candidates[:top_k]

    def fake_generate(question, chunks, conversation_history=None, technical=False, research=False):
        calls["generate"].append((len(chunks), research))
        return ("Respuesta con fundamento.", "modelo-gen", 100, 50) if chunks else ("No encontre informacion.", None, None, None)

    def fake_gate(question, answer, chunks):
        calls["gate"] += 1
        return True, "modelo-gate"

    monkeypatch.setattr(research, "generate_with_fallback", fake_plan)
    monkeypatch.setattr(research, "hybrid_search", fake_search)
    monkeypatch.setattr(research, "rerank", fake_rerank)
    monkeypatch.setattr(research, "generate_answer", fake_generate)
    monkeypatch.setattr(research, "answer_is_grounded_in_practice", fake_gate)
    return calls


def test_full_research_flow_uses_three_llm_calls_and_one_rerank(pipeline):
    response, _ = research.answer_question_research(None, "Que pasa si no pago un impuesto?")
    assert response.grounded is True
    assert pipeline["plan"] == 1 and pipeline["gate"] == 1
    assert len(pipeline["search"]) == 3  # pregunta + 2 subpreguntas
    assert len(pipeline["rerank"]) == 1 and pipeline["rerank"][0][1:] == (3, 8)  # una vez, sobre la union, con top_k=8
    assert pipeline["generate"] == [(3, True)]  # estilo de investigacion
    assert response.research.llm_calls == 3
    assert response.research.subquestions == ["quien debe pagar", "que plazo hay"]
    assert response.research.areas == ["fiscal"]
    assert response.research.documents_consulted == ["Codigo Fiscal"]
    assert response.agent_trace.route == "investigar"


def test_no_chunk_over_threshold_means_no_generation_and_no_gate(pipeline, monkeypatch):
    monkeypatch.setattr(research, "hybrid_search", lambda db, t, e, document_filter=None: [_chunk(1, "Ley X", "1", passed=False)])
    response, _ = research.answer_question_research(None, "Pregunta sin base")
    assert response.grounded is False
    assert pipeline["generate"] == [(0, True)]  # se llama sin fragmentos -> "no encontre"
    assert pipeline["gate"] == 0
    assert response.research.llm_calls == 1  # solo la planificacion


def test_out_of_scope_returns_fixed_message_without_any_llm_call(pipeline, monkeypatch):
    monkeypatch.setattr(research, "classify_intent", lambda q, question_embedding=None: (False, 0.1))
    response, _ = research.answer_question_research(None, "Cual es la capital de Francia?")
    assert response.answer == OUT_OF_SCOPE_MESSAGE and response.grounded is False
    assert pipeline["plan"] == 0 and pipeline["search"] == []


def test_capa1_is_skipped_inside_a_conversation(pipeline, monkeypatch):
    monkeypatch.setattr(research, "classify_intent", lambda q, question_embedding=None: (False, 0.1))
    response, _ = research.answer_question_research(None, "Y las multas?", conversation_history=[{"role": "user", "content": "x"}])
    assert response.answer != OUT_OF_SCOPE_MESSAGE


def test_smalltalk_is_answered_without_llm_calls(pipeline, monkeypatch):
    monkeypatch.setattr(research, "detect_smalltalk_response", lambda q: "Hola, soy LexChiapas.")
    response, _ = research.answer_question_research(None, "hola")
    assert response.answer == "Hola, soy LexChiapas." and pipeline["plan"] == 0


def test_planning_failure_falls_back_to_the_original_question(pipeline, monkeypatch):
    def boom(*a, **k):
        raise research.AllModelsFailedError("todos fallaron")

    monkeypatch.setattr(research, "generate_with_fallback", boom)
    response, _ = research.answer_question_research(None, "Pregunta compleja")
    assert len(pipeline["search"]) == 1 and response.research.subquestions == []
    assert response.grounded is True


def test_low_call_budget_skips_planning_but_never_the_gate(pipeline, monkeypatch):
    monkeypatch.setattr(research, "get_ai_config", lambda: {"agentic_rag": {"research": {"max_llm_calls": 2}}})
    response, _ = research.answer_question_research(None, "Pregunta")
    assert pipeline["plan"] == 0 and pipeline["gate"] == 1
    assert response.research.llm_calls == 2


def test_filler_after_admitting_no_information_downgrades_grounded(pipeline, monkeypatch):
    monkeypatch.setattr(
        research, "generate_answer",
        lambda q, chunks, conversation_history=None, technical=False, research=False:
        ("No hay informacion en los fragmentos. Generalmente se hace con un acta.", "modelo-gen", 1, 1),
    )
    response, _ = research.answer_question_research(None, "Como se constituye una sociedad anonima?")
    assert response.grounded is False and "Generalmente" not in response.answer


# --------------------------------------------------- guardia de relleno estructurada
STRUCTURED_OK = (
    "Que dice la ley: El Articulo 36 exige un permiso para poseer un animal peligroso.\n\n"
    "Como aplica: Normalmente el tramite se hace ante la Secretaria.\n\n"
    "Excepciones, reformas y derogaciones: No encontre excepciones ni reformas en los fragmentos recuperados.\n\n"
    "Que no cubre esta respuesta: No hay informacion sobre leyes federales."
)


def test_structured_answer_with_fixed_third_section_is_not_downgraded():
    cleaned, padded = research.apply_filler_guard(STRUCTURED_OK)
    assert padded is False and cleaned == STRUCTURED_OK


def test_structured_answer_admitting_no_info_in_first_section_loses_filler_but_keeps_last_section():
    answer = (
        "Que dice la ley: No hay informacion especifica sobre eso en los fragmentos.\n\n"
        "Como aplica: Generalmente se requiere un acta constitutiva.\n\n"
        "Excepciones, reformas y derogaciones: No encontre excepciones ni reformas en los fragmentos recuperados.\n\n"
        "Que no cubre esta respuesta: Normalmente conviene consultar a un abogado."
    )
    cleaned, padded = research.apply_filler_guard(answer)
    assert padded is True
    assert "acta constitutiva" not in cleaned
    assert "Normalmente conviene consultar a un abogado." in cleaned  # el cuarto rotulo no se toca
