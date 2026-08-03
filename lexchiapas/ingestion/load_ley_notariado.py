"""Script de ingesta puntual para la Ley del Notariado para el Estado de
Chiapas (area_derecho=civil).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.

No se toco app/rag/chunker.py: el texto de esta ley (formato estandar
TITULO/CAPITULO/ARTICULO, sin sufijos BIS/TER, sin sufijos -A/-B, sin
ordinales de titulo compuestos, con el mismo pie de pagina "dd/mm/aaaa
hh:mm p.m. N" que ya cubre FOOTER_RE) se valido con chunk_legal_text tal
cual y produjo 277 chunks, 0 sin articulo_numero, 0 numeros duplicados,
articulos 1-277 sin huecos.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley del Notariado para el Estado de Chiapas"

# El host viejo (consejeriajuridica.chiapas.gob.mx) devuelve 404 para este
# documento (confirmado con HEAD antes de descargar, 2026-07-13); el host
# nuevo institutodelaconsejeriajuridica.chiapas.gob.mx con la misma ruta y
# nombre de archivo respondio 200 OK, content-type application/pdf,
# content-length 421953, mismo patron ya visto con otras leyes recientes.
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/LEY%20DEL%20NOTARIADO%20PARA%20EL%20ESTADO%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/ley_notariado.txt"

# Leido del propio PDF: "Ultima reforma publicada en el Periodico Oficial
# No. 392, Decreto No. 008, Tomo III de fecha miercoles 03 de octubre de
# 2012." No hay una fecha de publicacion original explicita en el texto (el
# articulado transitorio solo da la fecha del decreto/promulgacion, 04 de
# noviembre de 2004, que no es necesariamente la fecha de publicacion en el
# Periodico Oficial); se deja fecha_publicacion en None para no reportar un
# dato no confirmado.
FECHA_PUBLICACION = None
FECHA_ULTIMA_REFORMA = date(2012, 10, 3)


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

        numeros = [c.articulo_numero for c in legal_chunks]
        duplicados = {n for n in numeros if numeros.count(n) > 1}
        print(f"numeros de articulo duplicados: {sorted(duplicados) if duplicados else 'ninguno'}")

        document = Document(
            nombre=DOCUMENT_NOMBRE,
            tipo="ley",
            fecha_publicacion=FECHA_PUBLICACION,
            fecha_ultima_reforma=FECHA_ULTIMA_REFORMA,
            source_url=SOURCE_URL,
            area_derecho="civil",
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
