"""Test de regresion real (usa la DB real, sin mocks de sesion) para el bug
de atomicidad corregido en app.workers.ingestion_tasks.ingest_document (ver
auditoria de base de datos, 2026-08-06).

No llama a la API de NVIDIA (embed_and_store_chunks se reemplaza por un fake
que simula el fallo a mitad de camino) -- solo ejercita Postgres real, sin
costo de API. Crea y borra su propio Document aislado (is_active=False,
nombre reconocible) para no tocar el corpus real.
"""

import pytest

from app.database import SessionLocal
from app.models import Chunk, Document, IngestionLog
from app.workers import ingestion_tasks

TEST_DOCUMENT_NOMBRE = "TEST_ATOMICITY_DOCUMENT_DO_NOT_USE_IN_PROD"


@pytest.fixture
def temp_document():
    db = SessionLocal()
    document = Document(nombre=TEST_DOCUMENT_NOMBRE, tipo="ley", is_active=False)
    db.add(document)
    db.commit()
    db.refresh(document)

    old_chunk = Chunk(document_id=document.id, content="OLD_CHUNK_MARKER", embedding=[0.0] * 1024)
    db.add(old_chunk)
    db.commit()

    document_id = document.id
    db.close()

    yield document_id

    cleanup_db = SessionLocal()
    cleanup_db.query(IngestionLog).filter(IngestionLog.document_id == document_id).delete()
    cleanup_db.query(Document).filter(Document.id == document_id).delete()
    cleanup_db.commit()
    cleanup_db.close()


def test_replace_existing_rolls_back_delete_when_embedding_fails_midway(temp_document, monkeypatch):
    # BUG REAL corregido 2026-08-06: antes de este fix, el DELETE de
    # replace_existing se commiteaba en su propia transaccion, separada del
    # INSERT de los chunks nuevos. Si embed_and_store_chunks fallaba a mitad
    # de camino (llamadas HTTP reales a NVIDIA, puede fallar en cualquier
    # chunk), los chunks VIEJOS ya estaban borrados y commiteados, los
    # NUEVOS nunca llegaban a insertarse -- la ley quedaba con 0 chunks
    # activos. Este fake simula exactamente ese fallo a mitad de camino: dos
    # llamadas reales a la app.rag.embeddings real generarian una race real,
    # pero para el test alcanza con reemplazar la funcion completa.
    def fake_embed_and_store_chunks(db, document, legal_chunks):
        db.add(Chunk(document_id=document.id, content="PARTIAL_NEW_CHUNK", embedding=[0.0] * 1024))
        raise RuntimeError("fallo simulado de NVIDIA a mitad del loop de embeddings")

    monkeypatch.setattr(ingestion_tasks, "embed_and_store_chunks", fake_embed_and_store_chunks)
    monkeypatch.setattr(ingestion_tasks, "chunk_legal_text", lambda raw_text, document_nombre: [])

    with pytest.raises(RuntimeError, match="fallo simulado"):
        ingestion_tasks.ingest_document(temp_document, raw_text="texto de prueba", replace_existing=True)

    db = SessionLocal()
    try:
        remaining = db.query(Chunk).filter(Chunk.document_id == temp_document).all()
        contents = {c.content for c in remaining}

        # El chunk viejo SIGUE ahi (el DELETE se revirtio junto con el
        # INSERT parcial) -- antes del fix, `remaining` habria sido [].
        assert "OLD_CHUNK_MARKER" in contents
        assert "PARTIAL_NEW_CHUNK" not in contents

        log = (
            db.query(IngestionLog)
            .filter(IngestionLog.document_id == temp_document)
            .order_by(IngestionLog.id.desc())
            .first()
        )
        assert log is not None
        assert log.status == "failed"
    finally:
        db.close()
