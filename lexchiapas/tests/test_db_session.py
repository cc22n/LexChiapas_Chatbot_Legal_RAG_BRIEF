from sqlalchemy import text

from app.database import SessionLocal, engine
from app.rag.db_session import release_connection


def test_release_connection_returns_connection_to_pool():
    # Una query de lectura abre una transaccion que retiene la conexion; es lo
    # que pasaba durante toda la llamada al LLM (auditoria 2026-10-21, CRIT-02).
    db = SessionLocal()
    try:
        baseline = engine.pool.checkedout()
        db.execute(text("SELECT 1"))
        assert engine.pool.checkedout() == baseline + 1

        release_connection(db)

        assert engine.pool.checkedout() == baseline
        # La misma sesion sigue siendo usable (abre una transaccion nueva sola).
        assert db.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        db.close()


def test_release_connection_tolerates_none():
    release_connection(None)
