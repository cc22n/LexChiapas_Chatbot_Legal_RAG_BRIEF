"""Script de ingesta puntual para la Ley del Servicio Civil del Estado y los
Municipios de Chiapas (area_derecho=laboral).

Sigue el mismo patron sincrono usado para las leyes anteriores (Amnistia,
Bibliotecas, Tortura, Adopcion, Codigo de Atencion a la Familia, Ley de los
Derechos de Ninas, Ninos y Adolescentes, Ley de Movilidad y Transporte):
sin Celery, ejecucion directa contra la DB real via app.database.SessionLocal().

Esta es la unica ley laboral ESTATAL disponible; la Ley Federal del Trabajo
es materia federal y queda fuera de alcance.

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley del Servicio Civil del Estado y los Municipios de Chiapas"

# El host viejo (consejeriajuridica.chiapas.gob.mx) devuelve 404 para este
# documento (confirmado con HEAD antes de descargar, mismo patron ya visto
# con otras leyes recientes). El host nuevo
# institutodelaconsejeriajuridica.chiapas.gob.mx tiene DOS archivos
# distintos para esta ley bajo el mismo directorio, con nombre de archivo
# distinto (guion bajo vs %20/espacio) y contenido distinto:
#   - .../pdf/LEY_DEL_SERVICIO_CIVIL_DEL_ESTADO_Y_LOS_MUNICIPIOS_DE_CHIAPAS.pdf
#     200 OK, Content-Length 477797, Last-Modified 2025-01-14. Texto interno:
#     "Ultima reforma publicada en el Periodico oficial No. 382, Decreto
#     No. 041, Tomo III de fecha miercoles 05 de diciembre de 2024".
#   - .../pdf/LEY%20DEL%20SERVICIO%20CIVIL%20DEL%20ESTADO%20Y%20LOS%20MUNICIPIOS%20DE%20CHIAPAS.pdf
#     200 OK, Content-Length 723376, Last-Modified 2024-10-11 (mas viejo).
#     Texto interno: "Ultima reforma publicada en el Periodico oficial
#     No. 141, Decreto No. 044, Tomo III de fecha miercoles 09 de diciembre
#     de 2020" -- version desactualizada (4 anos de reformas menos).
# Se uso la version con guion bajo (la mas reciente, confirmada leyendo el
# encabezado real de ambos PDFs, no solo el nombre de archivo).
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/LEY_DEL_SERVICIO_CIVIL_DEL_ESTADO_Y_LOS_MUNICIPIOS_DE_CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/ley_servicio_civil.txt"

# Leido del propio PDF: "Ultima reforma publicada en el Periodico oficial
# No. 382, Decreto No. 041, Tomo III de fecha miercoles 05 de diciembre de
# 2024".
FECHA_ULTIMA_REFORMA = date(2024, 12, 5)


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
        print(f"articulo_numero duplicados: {duplicados}")

        document = Document(
            nombre=DOCUMENT_NOMBRE,
            tipo="ley",
            fecha_publicacion=None,
            fecha_ultima_reforma=FECHA_ULTIMA_REFORMA,
            source_url=SOURCE_URL,
            area_derecho="laboral",
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
