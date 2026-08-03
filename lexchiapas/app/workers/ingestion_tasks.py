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
            db.query(Chunk).filter(Chunk.document_id == document_id).delete(synchronize_session=False)
            db.commit()

        legal_chunks = chunk_legal_text(raw_text, document_nombre=document.nombre)
        chunks_created = embed_and_store_chunks(db, document, legal_chunks)

        log.status = "success"
        log.chunks_created = chunks_created
        log.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"document_id": document_id, "chunks_created": chunks_created}
    except Exception as exc:
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
