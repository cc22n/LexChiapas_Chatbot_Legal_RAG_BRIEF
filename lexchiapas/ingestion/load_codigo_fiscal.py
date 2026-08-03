"""Script de ingesta puntual para el Codigo Fiscal del Estado de Chiapas
(area_derecho=fiscal).

Sigue el mismo patron sincrono usado para las leyes anteriores (Amnistia,
Bibliotecas, Tortura, Adopcion, Codigo de Atencion a la Familia, Ley de
Derechos de NNA, Ley de Movilidad y Transporte): sin Celery, ejecucion
directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.

Motivacion real: una prueba en vivo del bot con la pregunta "evasion de
impuestos en Chiapas" no encontro ninguna ley cargada. El Codigo Fiscal
cubre defraudacion fiscal (Titulo Quinto, Capitulo II, Articulo 217) e
infracciones/multas por evasion de contribuciones (Titulo Quinto, Capitulo
I, Seccion Cuarta, Articulos 202-204), asi que deberia resolver ese caso.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Codigo Fiscal del Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 1931973 bytes,
# Last-Modified 2025-12-16) el 2026-07-12. Encontrada en el listado HTML de
# "legislacion vigente" del Congreso del Estado (seccion CODIGOS, entrada
# #7), NO en ninguno de los dos hosts de Consejeria Juridica: el host nuevo
# (institutodelaconsejeriajuridica.chiapas.gob.mx) no listaba el Codigo
# Fiscal en su indice de Leyes, y el host viejo (consejeriajuridica.chiapas.
# gob.mx) no se probo por separado porque el Congreso ya dio un link directo
# valido. El Congreso sirve sus PDFs de "Info-Parlamentaria" con un query
# param de version (?v=...) que cambia con cada reforma; este es el vigente
# a la fecha de la reforma de diciembre 2025 (Decreto 036/040) mencionada en
# el brief original.
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0007.pdf?v=MzE="

PROCESSED_TXT = "data/processed/codigo_fiscal.txt"

# Leido del propio PDF (primera pagina): "ULTIMA REFORMA PUBLICADA EN EL
# PERIODICO OFICIAL NUMERO 076, DE FECHA 10 DE DICIEMBRE DE 2025. DECRETO
# NUMERO 040." El texto original (nueva creacion) se publico el 18 de mayo
# de 2016 segun la misma pagina.
FECHA_PUBLICACION = date(2016, 5, 18)
FECHA_ULTIMA_REFORMA = date(2025, 12, 10)


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
            fecha_publicacion=FECHA_PUBLICACION,
            fecha_ultima_reforma=FECHA_ULTIMA_REFORMA,
            source_url=SOURCE_URL,
            area_derecho="fiscal",
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
