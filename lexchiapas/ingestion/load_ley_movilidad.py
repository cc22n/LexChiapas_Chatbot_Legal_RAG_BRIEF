"""Script de ingesta puntual para la Ley de Movilidad y Transporte del Estado
de Chiapas (area_derecho=transito).

Sigue el mismo patron sincrono usado para las leyes anteriores (Amnistia,
Bibliotecas, Tortura, Adopcion, Codigo de Atencion a la Familia, Ley de los
Derechos de Ninas, Ninos y Adolescentes): sin Celery, ejecucion directa
contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de Movilidad y Transporte del Estado de Chiapas"
# El host viejo (consejeriajuridica.chiapas.gob.mx) devuelve 404 para este
# documento (confirmado con HEAD antes de descargar); el host nuevo
# institutodelaconsejeriajuridica.chiapas.gob.mx con la misma ruta y nombre
# de archivo respondio 200 OK, content-type application/pdf,
# content-length 317967, mismo patron ya visto con la Ley de los Derechos
# de NNA.
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/LEY%20DE%20MOVILIDAD%20Y%20TRANSPORTE%20DEL%20ESTADO"
    "%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/ley_movilidad_transporte.txt"

# Leido del propio PDF: "Ultima reforma publicada en el Periodico Oficial
# numero 090, Tomo III, de fecha 05 de febrero de 2026, Decreto numero 201".
FECHA_ULTIMA_REFORMA = date(2026, 2, 5)


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
            area_derecho="transito",
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
