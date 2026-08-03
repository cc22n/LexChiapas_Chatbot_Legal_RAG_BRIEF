from app.database import SessionLocal
from app.evaluation.run_golden_dataset import run_evaluation
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.evaluation_tasks.run_golden_dataset_task")
def run_golden_dataset_task() -> dict:
    """Corre el golden dataset completo (24 preguntas, ver
    app.evaluation.golden_dataset, ~35 minutos reales y llamadas reales a
    NVIDIA NIM/OpenAI/xAI) y persiste el resultado en golden_dataset_runs/
    golden_dataset_run_cases (ver app.evaluation.run_golden_dataset.
    run_evaluation).

    Disparo MANUAL unicamente, encolado por POST /admin/evaluation/run (ver
    app/api/admin.py) -- esta tarea NO esta en celery_app.conf.beat_schedule
    a proposito (WEB_FRONTEND_PLAN.md seccion 3.3, item 4): correrla
    automaticamente cada noche gastaria API real sin que el pipeline haya
    cambiado. El usuario decide cuando vale la pena re-medir (despues de un
    cambio real al retriever/reranker/generator/grounding).
    """
    db = SessionLocal()
    try:
        result = run_evaluation(db)
        return {
            "run_id": result["run_id"],
            "total": result["total"],
            "passed": result["passed"],
            "xfailed_known": result["xfailed_known"],
            "failed": result["failed"],
            "duration_ms": result["duration_ms"],
        }
    finally:
        db.close()
