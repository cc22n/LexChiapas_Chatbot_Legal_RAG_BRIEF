from dataclasses import dataclass, field

from app.evaluation.common import evaluate_case
from app.evaluation.golden_dataset import LIMITATION_TOLERATE_GROUNDED_FALSE, GoldenCase

# LIMITATION_TOLERATE_GROUNDED_FALSE (Fase 9.7, migracion real de
# embeddings 2026-08-27): inverso de LIMITATION_TOLERATE_GROUNDED_TRUE --
# tolera que el sistema admita honestamente "no encontre informacion" en
# un caso donde expects_grounded=True, pero NUNCA tolera un grounded=True
# que cite el articulo equivocado. Sin tests dedicados hasta ahora (la
# unica cobertura real de evaluate_case era tests/test_rag_regression.py,
# que cuesta API real) -- estos usan un stub minimo de ChatResponse.


@dataclass
class _FakeChunk:
    articulo_numero: str
    document_nombre: str


@dataclass
class _FakeResponse:
    grounded: bool
    answer: str = "una respuesta"
    retrieved_chunks: list = field(default_factory=list)


def _case(**overrides) -> GoldenCase:
    defaults = dict(
        name="test_caso_borde",
        question="pregunta de prueba",
        ley_contains="Ley de Prueba",
        articulo_esperado="5",
        expects_grounded=True,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_FALSE,
        known_limitation_reason="similitud real por debajo del threshold, verificado",
    )
    defaults.update(overrides)
    return GoldenCase(**defaults)


def test_tolerates_honest_grounded_false():
    case = _case()
    response = _FakeResponse(grounded=False, retrieved_chunks=[])
    result = evaluate_case(case, response)
    assert result.status == "xfailed_known"
    assert "caso borde de similarity_threshold" in result.reason


def test_passes_when_grounded_true_and_correct_article_found():
    case = _case()
    response = _FakeResponse(
        grounded=True,
        retrieved_chunks=[_FakeChunk(articulo_numero="5", document_nombre="Ley de Prueba para el Estado")],
    )
    result = evaluate_case(case, response)
    assert result.status == "passed"
    assert result.position == 1


def test_passes_when_grounded_true_and_alt_law_matches():
    case = _case(alt_ley_contains="ley alternativa", alt_articulos=("9",))
    response = _FakeResponse(
        grounded=True,
        retrieved_chunks=[_FakeChunk(articulo_numero="9", document_nombre="Ley Alternativa de Chiapas")],
    )
    result = evaluate_case(case, response)
    assert result.status == "passed"


def test_never_tolerates_grounded_true_with_wrong_article():
    # El caso peligroso: grounded=True pero cito una ley/articulo distinto
    # al esperado -- esto NUNCA debe pasar como "passed" ni "xfailed_known".
    case = _case()
    response = _FakeResponse(
        grounded=True,
        retrieved_chunks=[_FakeChunk(articulo_numero="99", document_nombre="Otra Ley Totalmente Distinta")],
    )
    result = evaluate_case(case, response)
    assert result.status == "failed"
    assert "no se tolera un falso positivo" in result.reason
