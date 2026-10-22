from sqlalchemy.orm import Session


def release_connection(db: Session | None) -> None:
    """Cierra la transaccion abierta de la sesion para devolver la conexion
    al pool ANTES de una llamada larga a un LLM.

    Hallazgo de la auditoria 2026-10-21 (CRIT-02): la primera query de
    retrieval abre una transaccion que, sin commit/rollback, retiene una de
    las 15 conexiones del pool durante toda la generacion + grounding (3-12 s
    de red). Con ~16 turnos concurrentes el pool se agota (pool_timeout=10).

    Solo se llama en puntos donde la sesion tiene unicamente LECTURAS
    pendientes (retrieval), asi que rollback no descarta nada que importe. La
    siguiente query de la misma sesion abre una transaccion nueva sola.
    """
    if db is not None:
        db.rollback()
