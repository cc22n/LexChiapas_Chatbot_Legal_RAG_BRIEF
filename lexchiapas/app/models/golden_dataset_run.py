from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GoldenDatasetRun(Base):
    """Una corrida completa del golden dataset real (24 preguntas, ver
    app.evaluation.golden_dataset) contra app.rag.rag_pipeline.answer_question
    (WEB_FRONTEND_PLAN.md seccion 3.3). Disparada manualmente via
    POST /admin/evaluation/run (app.workers.evaluation_tasks.
    run_golden_dataset_task) -- NUNCA por Celery Beat, cada corrida cuesta
    ~35 minutos y llamadas reales a NVIDIA NIM/OpenAI/xAI.

    passed/xfailed_known/failed son mutuamente excluyentes y suman `total`
    (mismo criterio que "17 passed, 2 xfailed, 5 failed" del baseline
    documentado en tests/test_rag_regression.py) -- xfailed_known son casos
    con una limitacion YA CONOCIDA y documentada (ver
    app.evaluation.golden_dataset.GoldenCase.known_limitation), no fallos
    reales."""

    __tablename__ = "golden_dataset_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[int | None] = mapped_column(Integer)
    xfailed_known: Mapped[int | None] = mapped_column(Integer)
    failed: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    cases = relationship(
        "GoldenDatasetRunCase", back_populates="run", cascade="all, delete-orphan"
    )


class GoldenDatasetRunCase(Base):
    """Detalle por caso de una GoldenDatasetRun -- una fila por pregunta del
    golden dataset (24 por corrida completa). `passed` es True tanto para un
    caso limpio como para uno xfailed_known (mismo criterio que pytest: un
    xfail tolerado no es un FAILED); para distinguir un xfailed_known de un
    passed limpio, comparar expects_grounded contra actual_grounded (si
    difieren y passed=True, fue un caso tolerado) o revisar si
    articulo_esperado esta presente pero posicion_encontrada es None con
    passed=True (limitacion de retrieval tolerada, ver GoldenCase.
    limitation_kind=tolerate_missing_position) -- el conteo agregado
    xfailed_known real vive en GoldenDatasetRun, calculado en el momento de
    la corrida (app.evaluation.run_golden_dataset), no derivado despues de
    estas filas.

    respuesta_snippet guarda solo los primeros ~200 caracteres de la
    respuesta real (no el texto completo) -- alcanza para debug sin
    persistir contenido legal completo en una tabla de metricas."""

    __tablename__ = "golden_dataset_run_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("golden_dataset_runs.id", ondelete="CASCADE"), nullable=False
    )
    pregunta: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    expects_grounded: Mapped[bool | None] = mapped_column(Boolean)
    actual_grounded: Mapped[bool | None] = mapped_column(Boolean)
    articulo_esperado: Mapped[str | None] = mapped_column(String(50))
    posicion_encontrada: Mapped[int | None] = mapped_column(Integer)
    respuesta_snippet: Mapped[str | None] = mapped_column(String(250))

    run = relationship("GoldenDatasetRun", back_populates="cases")
