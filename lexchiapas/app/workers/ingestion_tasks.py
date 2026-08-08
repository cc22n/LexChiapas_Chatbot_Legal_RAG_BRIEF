import traceback
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Chunk, Document, IngestionLog
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.ingestion_tasks.ingest_document")
def ingest_document(document_id: int, raw_text: str, replace_existing: bool = False) -> dict:
    """Parte, genera embeddings y guarda los chunks de un documento ya creado.

    El scraping/parsing de PDF/HTML pasa antes de esta tarea (ver
    ingestion/scrapers y ingestion/parsers); aqui solo se corre chunking +
    embeddings + guardado, que es lo que puede tardar y por eso va en Celery.

    replace_existing=False (default, preserva el comportamiento historico de
    los scripts load_*.py, que siempre ingieren documentos nuevos sin chunks
    previos): los chunks generados se AGREGAN a los que ya existan para
    document_id.

    replace_existing=True (usado por app.workers.update_tasks.
    check_for_law_updates cuando detecta que una ley ya cargada se
    re-publico con una URL distinta): borra primero todos los chunks
    existentes de este document_id, antes de insertar los nuevos. Sin esto,
    reingerir un documento que YA tiene chunks dejaria chunks VIEJOS (texto
    de la ley posiblemente ya reformado/incorrecto) y chunks NUEVOS
    coexistiendo en la misma busqueda -- un bug real de correctitud para un
    RAG legal, no solo cosmetico.
    """
    db = SessionLocal()
    log = IngestionLog(document_id=document_id, status="running", started_at=datetime.now(timezone.utc))
    db.add(log)
    db.commit()
    db.refresh(log)

    try:
        document = db.get(Document, document_id)
        if document is None:
            raise ValueError(f"document_id {document_id} no existe")

        if replace_existing:
            # BUG REAL (auditoria de base de datos, 2026-08-06): antes este
            # DELETE se commiteaba aca mismo, en su propia transaccion,
            # separada del INSERT de los chunks nuevos (que llega recien al
            # final de embed_and_store_chunks, despues de N llamadas HTTP
            # reales a NVIDIA por cada trozo -- puede fallar a mitad de
            # camino). Si esa llamada fallaba, el except de abajo solo
            # marcaba el log como failed: los chunks VIEJOS ya estaban
            # borrados y commiteados, los NUEVOS nunca llegaron a insertarse
            # -- la ley quedaba con 0 chunks activos, indistinguible de "esta
            # ley no esta en el corpus" para un RAG legal donde esa es una
            # respuesta valida. Sin commit aca, el DELETE queda pendiente en
            # la MISMA transaccion que el commit final de
            # embed_and_store_chunks: o se reemplazan los chunks completos,
            # o (ver except abajo) se hace rollback y quedan los viejos.
            db.query(Chunk).filter(Chunk.document_id == document_id).delete(synchronize_session=False)

        legal_chunks = chunk_legal_text(raw_text, document_nombre=document.nombre)
        chunks_created = embed_and_store_chunks(db, document, legal_chunks)

        log.status = "success"
        log.chunks_created = chunks_created
        log.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"document_id": document_id, "chunks_created": chunks_created}
    except Exception as exc:
        # Descarta el DELETE (si replace_existing) y cualquier Chunk nuevo
        # que ya se haya agregado a la sesion antes de que embed_text
        # fallara -- sin esto, el commit de mas abajo (que solo pretende
        # guardar el estado failed del log) commitearia tambien ese estado
        # parcial. Con el rollback, los chunks VIEJOS quedan intactos si
        # replace_existing fallo a mitad de camino.
        db.rollback()
        log.status = "failed"
        # Fase 4, hallazgo real: `str(exc)` solo captura el mensaje final,
        # no donde ni por que trueno -- para un chunking/embedding real que
        # falla a la mitad de cientos de articulos, eso no alcanza para
        # debuggear sin volver a reproducirlo a mano. Mismo patron ya
        # establecido para Message.error_message (Fase 3.7): guardar el
        # traceback completo, truncado a 4000 caracteres.
        log.error_message = "".join(traceback.format_exception(exc))[:4000]
        log.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise
    finally:
        db.close()
