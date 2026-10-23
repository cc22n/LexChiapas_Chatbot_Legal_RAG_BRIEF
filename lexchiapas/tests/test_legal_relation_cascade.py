from app.database import SessionLocal
from app.models.chunk import EMBEDDING_DIMENSION, Chunk
from app.models.document import Document
from app.models.legal_relation import LegalRelation


def test_deleting_chunks_removes_their_relations_like_replace_existing_does():
    # Reproduce el borrado de replace_existing (ingestion_tasks.py): sin
    # ON DELETE CASCADE en legal_relations.from_chunk_id esto lanzaba
    # ForeignKeyViolation (auditoria 2026-10-21, ALT-03). Todo se descarta con
    # rollback: no se escribe nada en la DB.
    db = SessionLocal()
    try:
        doc = Document(nombre="TEST-CASCADE-borrar", tipo="ley", is_active=False)
        db.add(doc)
        db.flush()
        chunk = Chunk(document_id=doc.id, content="articulo de prueba", embedding=[0.0] * EMBEDDING_DIMENSION)
        db.add(chunk)
        db.flush()
        db.add(
            LegalRelation(
                from_document_id=doc.id,
                from_chunk_id=chunk.id,
                from_articulo="1",
                relation_type="reforma",
                to_law_name_raw="Ley de prueba",
                source_text="(REFORMADO, P.O. 1 DE ENERO DE 2020)",
                extraction_method="regex",
            )
        )
        db.flush()

        db.query(Chunk).filter(Chunk.document_id == doc.id).delete(synchronize_session=False)
        db.flush()

        remaining = db.query(LegalRelation).filter(LegalRelation.from_document_id == doc.id).count()
        assert remaining == 0
    finally:
        db.rollback()
        db.close()
