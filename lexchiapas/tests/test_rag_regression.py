"""Set de regresion real (extremo a extremo) del pipeline RAG completo.

Este archivo NO usa mocks. Cada caso llama a
app.rag.rag_pipeline.answer_question(db, pregunta) contra la base de datos
real (Postgres/pgvector) y la API real de NVIDIA NIM (embeddings +
generacion). Esto es intencional: es la unica forma de medir el pipeline tal
como esta hoy, no una version simulada. Cada caso gasta llamadas reales a la
API -- no correr este archivo en CI sin cuidado del costo/rate limit.

Requiere: DATABASE_URL apuntando a la DB real con el corpus cargado
(is_active=True) y una API key de NVIDIA NIM valida en el entorno (.env via
app.config.Settings). Si esas dependencias no estan disponibles, estos tests
fallaran con errores de conexion, no con AssertionError -- eso es correcto,
no un bug de este archivo.

Snapshot del corpus usado para armar este set (~20 documentos activos,
verificado por consulta directa a `documents`/`chunks` antes de escribir las
preguntas): penal (Ley de Amnistia, doc 4; Codigo Penal para el Estado de
Chiapas, doc 24 -- agregado en Fase 3.7 via el scraper de Congreso, ver
PLAN.md), cultural (Ley de Bibliotecas, doc
7), derechos_humanos (Ley de Tortura, doc 8), familiar (Ley de Adopcion doc
9, Codigo de Atencion a la Familia doc 10, Ley de Ninas Ninos y Adolescentes
doc 11), transito (Ley de Movilidad y Transporte, doc 12), fiscal (Codigo
Fiscal, doc 13), salud (Ley de Salud, doc 14), civil (Ley del Notariado doc
15, Codigo Civil Libro 1 doc 20, Libro 2 doc 21, Libro 3 doc 22, Libro 4 doc
23), laboral (Ley del Servicio Civil, doc 16), administrativo (Ley de
Transparencia, doc 17), ambiental (Ley Ambiental, doc 19).

Cada respuesta correcta esperada (numero de articulo + ley) fue verificada
leyendo el chunk real en la base de datos ANTES de escribir la pregunta --
no se invento ningun numero de articulo. El detalle caso-por-caso (que se
espera y por que, incluyendo los 3 casos con limitacion conocida) vive ahora
en app/evaluation/golden_dataset.py (WEB_FRONTEND_PLAN.md seccion 3.3, item
1) -- ESTE archivo antes tenia 24 funciones test_* separadas con la
pregunta/expectativa hardcodeada; se parametrizo sobre GOLDEN_DATASET para
que pytest y el evaluador real (app.evaluation.run_golden_dataset) compartan
un solo dato, sin duplicar mantenimiento. Los docstrings originales de cada
caso (con el hallazgo real que motivo cada expectativa) se preservaron
integros en golden_dataset.py, no se perdieron en el refactor.

Si un caso falla por una limitacion de retrieval ya conocida (ej. el
reranker placeholder no trae el articulo correcto al top-K aunque si paso el
threshold), eso se documenta via pytest.xfail() con el motivo real de esta
corrida -- no se oculta ni se fuerza a pasar (ver
app.evaluation.common.evaluate_case, que decide passed/xfailed_known/failed
para cada caso).

BASELINE REAL (corrida completa de esta sesion, `pytest tests/test_rag_regression.py -v -s`,
2086.72s = 34m47s totales, 24 tests, contra el corpus completo real):
17 passed, 2 xfailed (limitaciones ya conocidas de PLAN.md, confirmadas
vigentes: tortura-sanciones bajo threshold, Art. 1576 sucesion fuera del
top-K), 5 failed (hallazgos NUEVOS de esa corrida: 2 son solapamiento real
entre leyes que compiten por el top-K -- Codigo Civil vs Ley de Adopcion, y
un articulo de definiciones largo que diluye la senal semantica -- adulto
mayor; 3 son casos donde lenguaje legal generico/boilerplate de OTRAS leyes
cruza el similarity_threshold=0.5 sin responder la pregunta real). Ningun
test fallo por una alucinacion real (articulo inventado que no existe en el
corpus); todos los "falsos positivos" de `grounded` citaron articulos REALES,
solo que no eran los mas pertinentes. Este baseline no cambio con el
refactor de parametrize (solo se movieron los datos, la logica de
passed/xfailed/failed en app.evaluation.common.evaluate_case reproduce
exactamente el comportamiento de las 24 funciones test_* originales).
"""

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.evaluation.common import article_position, evaluate_case
from app.evaluation.golden_dataset import GOLDEN_DATASET
from app.rag.rag_pipeline import answer_question


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    # Fase 3.7 (cache semantico, ver app.rag.semantic_cache): TODAS las
    # preguntas de este archivo se llaman sin conversation_history, asi que
    # TODAS pasan por el cache. Sin este truncate, una segunda corrida de
    # este archivo despues de un cambio de codigo real (retriever/reranker/
    # grounding) devolveria respuestas CACHEADAS de la corrida anterior en
    # vez de ejercitar el pipeline real -- exactamente lo que este set de
    # regresion existe para evitar. Se limpia una vez por modulo, antes de
    # las 24 preguntas.
    session.execute(text("TRUNCATE TABLE semantic_cache"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _run(db, question: str):
    """Corre el pipeline real y regresa (response, elapsed_ms)."""
    response, elapsed_ms = answer_question(db, question)
    return response, elapsed_ms


def _article_position(response, ley_contains: str, articulo: str) -> int | None:
    """Posicion (1-indexed) del chunk esperado dentro de retrieved_chunks, o
    None si no aparece. `ley_contains` es un substring case-insensitive del
    nombre del documento (para no depender de mayusculas/acentos exactos).

    Delega en app.evaluation.common.article_position (misma logica exacta,
    ahora compartida con el evaluador del golden dataset para no
    duplicarla) -- se preserva esta funcion tal cual (mismo nombre/firma/
    comportamiento) porque varios tests/notas la referencian por nombre.
    """
    return article_position(response, ley_contains, articulo)


def _report(question, response, elapsed_ms, expected_articulo=None, ley_contains=None):
    """Imprime un resumen legible del resultado real (baseline). pytest solo
    muestra esto con -s o cuando el test falla, pero sirve como evidencia
    grabada en el historial de ejecucion (ver reporte de la tarea)."""
    print(f"\n--- PREGUNTA: {question!r}")
    print(f"    grounded={response.grounded} modelo={response.llm_model} tiempo_ms={elapsed_ms}")
    print(f"    respuesta: {response.answer[:200]!r}")
    for i, c in enumerate(response.retrieved_chunks, start=1):
        marker = ""
        if expected_articulo and ley_contains:
            if c.articulo_numero == expected_articulo and ley_contains.lower() in c.document_nombre.lower():
                marker = "  <-- ESPERADO"
        print(f"    [{i}] {c.document_nombre} Art.{c.articulo_numero} sim={c.similarity:.3f}{marker}")
    if expected_articulo and ley_contains:
        pos = _article_position(response, ley_contains, expected_articulo)
        print(f"    posicion del articulo esperado en retrieved_chunks: {pos!r}")


@pytest.mark.parametrize("case", GOLDEN_DATASET, ids=[c.name for c in GOLDEN_DATASET])
def test_golden_case(db, case):
    """Un caso parametrizado del golden dataset real (ver
    app/evaluation/golden_dataset.py para la pregunta/expectativa completa
    de `case`, con el docstring/hallazgo real que la motivo).

    La logica de passed/xfailed_known/failed vive en
    app.evaluation.common.evaluate_case (compartida con
    app.evaluation.run_golden_dataset, el evaluador real detras de
    POST /admin/evaluation/run) -- este test solo corre el pipeline real,
    imprime el reporte legible (_report, igual que antes) y traduce el
    resultado de evaluate_case a xfail/assert de pytest.
    """
    response, elapsed_ms = _run(db, case.question)
    _report(
        case.question,
        response,
        elapsed_ms,
        expected_articulo=case.articulo_esperado,
        ley_contains=case.ley_contains,
    )

    result = evaluate_case(case, response)

    if result.status == "xfailed_known":
        pytest.xfail(result.reason)

    assert result.status == "passed", result.reason
