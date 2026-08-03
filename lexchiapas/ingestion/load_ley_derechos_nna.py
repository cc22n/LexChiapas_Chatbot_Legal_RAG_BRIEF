"""Script de ingesta puntual para la Ley de los Derechos de Ninas, Ninos y
Adolescentes del Estado de Chiapas (area_derecho=familiar).

Sigue el mismo patron sincrono usado para las leyes anteriores (Amnistia,
Bibliotecas, Tortura, Adopcion, Codigo de Atencion a la Familia): sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de los Derechos de Ninas, Ninos y Adolescentes del Estado de Chiapas"
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/LEY%20DE%20LOS%20DERECHOS%20DE%20NI%C3%91AS%2C%20NI%C3%91OS"
    "%20Y%20ADOLESCENTES%20DEL%20ESTADO%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/ley_derechos_nna.txt"

# Leido del propio PDF: "Ultima reforma publicada en el Periodico oficial
# No. 229, Decreto No. 248, Tomo III de fecha miercoles 15 de junio de 2022".
FECHA_ULTIMA_REFORMA = date(2022, 6, 15)


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.nombre == DOCUMENT_NOMBRE).first()
        if existing is not None:
            print(f"Documento ya existe (id={existing.id}), no se vuelve a ingerir.")
            return

        with open(PROCESSED_TXT, encoding="utf-8") as f:
            raw_text = f.read()

        legal_chunks = chunk_legal_text(raw_text, document_nombre=DOCUMENT_NOMBRE)
        print(f"chunk_legal_text produjo {len(legal_chunks)} chunks")
        sin_articulo = sum(1 for c in legal_chunks if c.articulo_numero is None)
        print(f"chunks sin articulo_numero: {sin_articulo}")

        document = Document(
            nombre=DOCUMENT_NOMBRE,
            tipo="ley",
            fecha_publicacion=None,
            fecha_ultima_reforma=FECHA_ULTIMA_REFORMA,
            source_url=SOURCE_URL,
            area_derecho="familiar",
            is_active=True,
        )
        db.add(document)
        db.flush()
        print(f"Document creado con id={document.id}")

        created = embed_and_store_chunks(db, document, legal_chunks)
        print(f"chunks guardados con embeddings: {created}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
