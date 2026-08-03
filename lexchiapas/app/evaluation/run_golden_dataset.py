"""Evaluador real del golden dataset (WEB_FRONTEND_PLAN.md seccion 3.3, item
3): corre CADA caso de app.evaluation.golden_dataset.GOLDEN_DATASET contra
app.rag.rag_pipeline.answer_question de verdad (misma llamada real que usa
el bot en produccion, mismo costo de API que tests/test_rag_regression.py --
no hay forma barata de medir esto), compara con
app.evaluation.common.evaluate_case (la MISMA logica que usa el test
parametrizado, para que pytest y este evaluador nunca diverjan en el
criterio de passed/xfailed/failed), y persiste el resultado en
golden_dataset_runs/golden_dataset_run_cases.

Disparo: solo via app.workers.evaluation_tasks.run_golden_dataset_task
(Celery, encolado por POST /admin/evaluation/run) -- NUNCA sincrono desde un
endpoint HTTP (~35 minutos reales excede cualquier timeout razonable) y
NUNCA por Celery Beat (gastaria API real sin que el pipeline haya cambiado).
"""

import time
import traceback
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.evaluation.common import evaluate_case
from app.evaluation.golden_dataset import GOLDEN_DATASET
from app.models.golden_dataset_run import GoldenDatasetRun, GoldenDatasetRunCase
from app.rag.rag_pipeline import answer_question

RESPUESTA_SNIPPET_MAX_CHARS = 200


def run_evaluation(db: Session) -> dict:
    """Corre las 24 preguntas del golden dataset real, persiste una fila de
    GoldenDatasetRun + una GoldenDatasetRunCase por pregunta, y devuelve un
    resumen (total, passed, xfailed_known, failed, duration_ms) + detalle.

    Cada caso se persiste inmediatamente despues de evaluarse (no en un solo
    commit al final) -- si la corrida completa (~35 min reales) se
    interrumpe a mitad de camino (ej. NVIDIA NIM caido, proceso matado), las
    preguntas ya evaluadas quedan guardadas en vez de perderse todas.

    Si UNA pregunta individual truena (excepcion real del pipeline, no un
    resultado grounded=False legitimo), se registra esa fila como failed con
    el error en respuesta_snippet y se sigue con la siguiente -- una falla
    puntual de API en la pregunta 12 de 24 no debe tirar las otras 23 que si
    se pudieron medir.
    """
    run = GoldenDatasetRun(started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    db.refresh(run)

    start = time.monotonic()
    passed = 0
    xfailed_known = 0
    failed = 0
    detail: list[dict] = []

    for case in GOLDEN_DATASET:
        try:
            response, _elapsed_ms = answer_question(db, case.question)
            result = evaluate_case(case, response)
            actual_grounded = result.actual_grounded
            position = result.position
            snippet = (response.answer or "")[:RESPUESTA_SNIPPET_MAX_CHARS]
            status = result.status
            reason = result.reason
        except Exception as exc:  # pragma: no cover - solo en fallo real de API/pipeline
            actual_grounded = None
            position = None
            snippet = ("ERROR: " + "".join(traceback.format_exception(exc)))[:RESPUESTA_SNIPPET_MAX_CHARS]
            status = "failed"
            reason = f"excepcion real corriendo el pipeline: {exc}"

        if status == "passed":
            passed += 1
        elif status == "xfailed_known":
            xfailed_known += 1
        else:
            failed += 1

        case_row = GoldenDatasetRunCase(
            run_id=run.id,
            pregunta=case.question,
            passed=(status != "failed"),
            expects_grounded=case.expects_grounded,
            actual_grounded=actual_grounded,
            articulo_esperado=case.articulo_esperado,
            posicion_encontrada=position,
            respuesta_snippet=snippet,
        )
        db.add(case_row)
        db.commit()

        detail.append(
            {
                "name": case.name,
                "question": case.question,
                "status": status,
                "expects_grounded": case.expects_grounded,
                "actual_grounded": actual_grounded,
                "articulo_esperado": case.articulo_esperado,
                "posicion_encontrada": position,
                "reason": reason,
            }
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    run.completed_at = datetime.now(timezone.utc)
    run.total = len(GOLDEN_DATASET)
    run.passed = passed
    run.xfailed_known = xfailed_known
    run.failed = failed
    run.duration_ms = duration_ms
    db.commit()

    return {
        "run_id": run.id,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "total": run.total,
        "passed": passed,
        "xfailed_known": xfailed_known,
        "failed": failed,
        "duration_ms": duration_ms,
        "detail": detail,
    }
