"""Logica de evaluacion compartida entre tests/test_rag_regression.py y
app.evaluation.run_golden_dataset -- una sola implementacion de
"donde quedo el articulo esperado en retrieved_chunks" y "paso o no paso
este caso", para no duplicarla entre pytest y el evaluador real
(WEB_FRONTEND_PLAN.md seccion 3.3, item 2).
"""

from dataclasses import dataclass
from typing import Any

from app.evaluation.golden_dataset import (
    LIMITATION_TOLERATE_GROUNDED_TRUE,
    LIMITATION_TOLERATE_MISSING_POSITION,
    GoldenCase,
)


def article_position(response: Any, ley_contains: str, articulo: str) -> int | None:
    """Posicion (1-indexed) del chunk esperado dentro de response.retrieved_chunks,
    o None si no aparece. `ley_contains` es un substring case-insensitive del
    nombre del documento (para no depender de mayusculas/acentos exactos).

    Misma logica exacta que la funcion _article_position original de
    tests/test_rag_regression.py -- movida aca para que el evaluador real
    (run_golden_dataset) la reuse en vez de duplicarla; el test file ahora
    delega en esta funcion.
    """
    for i, chunk in enumerate(response.retrieved_chunks, start=1):
        if (
            chunk.articulo_numero == articulo
            and ley_contains.lower() in chunk.document_nombre.lower()
        ):
            return i
    return None


def _alt_law_matches(response: Any, case: GoldenCase) -> bool:
    """Solo relevante para test_familiar_adopcion_requisitos (ver
    GoldenCase.alt_ley_contains): compara por startswith (no por "in"),
    identico al chequeo original en tests/test_rag_regression.py."""
    if not case.alt_ley_contains or not case.alt_articulos:
        return False
    return any(
        chunk.document_nombre.lower().startswith(case.alt_ley_contains.lower())
        and chunk.articulo_numero in case.alt_articulos
        for chunk in response.retrieved_chunks
    )


@dataclass(frozen=True)
class CaseEvaluation:
    case: GoldenCase
    # "passed" | "xfailed_known" | "failed" -- xfailed_known es un resultado
    # TOLERADO (no cuenta como fallo real), igual que pytest.xfail() no
    # cuenta como FAILED en el resumen de pytest.
    status: str
    actual_grounded: bool | None
    position: int | None
    reason: str


def evaluate_case(case: GoldenCase, response: Any) -> CaseEvaluation:
    """Compara la respuesta REAL del pipeline (app.rag.rag_pipeline.answer_question)
    contra lo esperado en `case`, reproduciendo exactamente la logica de
    assert/xfail que tenia cada funcion test_* original en
    tests/test_rag_regression.py antes de este refactor.

    No corre el pipeline -- recibe la ChatResponse ya generada, para que
    tests/test_rag_regression.py y app.evaluation.run_golden_dataset.run_evaluation
    puedan llamarla sobre respuestas obtenidas de formas distintas (fixture
    de pytest vs. sesion propia del evaluador) sin duplicar el criterio de
    passed/xfailed/failed.
    """
    actual_grounded = response.grounded
    position: int | None = None
    if case.articulo_esperado and case.ley_contains:
        position = article_position(response, case.ley_contains, case.articulo_esperado)

    # --- Casos con limitacion conocida documentada (xfail condicional) ---
    if case.limitation_kind == LIMITATION_TOLERATE_GROUNDED_TRUE:
        if actual_grounded:
            return CaseEvaluation(
                case=case,
                status="xfailed_known",
                actual_grounded=actual_grounded,
                position=position,
                reason=(
                    "limitacion conocida ya no reproduce: se esperaba "
                    f"grounded=False documentado pero esta corrida dio "
                    f"grounded=True -- {case.known_limitation_reason}"
                ),
            )
        if not response.answer.strip():
            return CaseEvaluation(
                case=case,
                status="failed",
                actual_grounded=actual_grounded,
                position=position,
                reason="grounded=False como se esperaba, pero la respuesta vino vacia",
            )
        return CaseEvaluation(
            case=case, status="passed", actual_grounded=actual_grounded, position=position, reason=""
        )

    if case.limitation_kind == LIMITATION_TOLERATE_MISSING_POSITION:
        if actual_grounded is not True:
            return CaseEvaluation(
                case=case,
                status="failed",
                actual_grounded=actual_grounded,
                position=position,
                reason=(
                    "grounded=True es un assert duro para este caso (gate "
                    "anti-alucinacion, no el ranking) -- no se tolera False"
                ),
            )
        if position is None:
            return CaseEvaluation(
                case=case,
                status="xfailed_known",
                actual_grounded=actual_grounded,
                position=position,
                reason=f"limitacion de retrieval conocida: {case.known_limitation_reason}",
            )
        return CaseEvaluation(
            case=case, status="passed", actual_grounded=actual_grounded, position=position, reason=""
        )

    # --- Casos estandar (sin limitacion conocida) ---
    if actual_grounded != case.expects_grounded:
        return CaseEvaluation(
            case=case,
            status="failed",
            actual_grounded=actual_grounded,
            position=position,
            reason=f"grounded esperado={case.expects_grounded} real={actual_grounded}",
        )

    if case.expects_empty_retrieval:
        if response.retrieved_chunks or response.llm_model is not None:
            return CaseEvaluation(
                case=case,
                status="failed",
                actual_grounded=actual_grounded,
                position=position,
                reason=(
                    "fuera de dominio total: se esperaba retrieved_chunks=[] "
                    "y llm_model=None (Capa 1 de guardrails debio rechazar "
                    "antes de gastar en hybrid_search/generacion)"
                ),
            )
        return CaseEvaluation(
            case=case, status="passed", actual_grounded=actual_grounded, position=position, reason=""
        )

    if case.articulo_esperado and case.ley_contains:
        alt_match = _alt_law_matches(response, case)
        if position is None and not alt_match:
            reason = (
                f"articulo esperado {case.articulo_esperado} ({case.ley_contains}) "
                "no aparecio en retrieved_chunks"
            )
            if case.alt_ley_contains:
                reason += (
                    f" (alternativa {case.alt_ley_contains} "
                    f"{case.alt_articulos} tampoco)"
                )
            return CaseEvaluation(
                case=case, status="failed", actual_grounded=actual_grounded, position=position, reason=reason
            )
        return CaseEvaluation(
            case=case, status="passed", actual_grounded=actual_grounded, position=position, reason=""
        )

    return CaseEvaluation(
        case=case, status="passed", actual_grounded=actual_grounded, position=position, reason=""
    )
