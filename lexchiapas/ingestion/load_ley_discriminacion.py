"""Script de ingesta puntual para la Ley que Previene y Combate la
Discriminacion en el Estado de Chiapas (area_derecho=derechos_humanos).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="derechos_humanos" (no un valor nuevo) porque es el
mismo valor ya usado para la Ley Estatal para Prevenir y Sancionar la
Tortura (documents.id 8) y para las demas leyes de derechos fundamentales
cargadas en esta misma tanda (Ley de Derechos y Culturas Indigenas, Ley de
Victimas, Ley en Materia de Desaparicion de Personas): esta ley regula la
prevencion y combate a la discriminacion (definicion de conductas
discriminatorias, Consejo Estatal para Prevenir y Eliminar la
Discriminacion, medidas de nivelacion e inclusion). Se comparo contenido
contra otros documentos que mencionan "actos discriminatorios" en chunks
existentes: cero resultados, sin overlap.

Fechas leidas del propio PDF (encabezado, primeras lineas): "PUBLICADA EN EL
PERIODICO OFICIAL DEL ESTADO No. 156 DE FECHA 03 DE ABRIL DE 2009. DECRETO
NUMERO 208" (publicacion original) y "(ULTIMA REFORMA MEDIANTE DECRETO 042,
PUBLICADA EN EL P.O. NUM 343-2a.SECCION TOMO III. DE FECHA 24 DE ENERO DE
2018.)" (ultima reforma).

Hallazgos reales del chunking: 76 chunks, 0 sin articulo_numero, rango
1-76, SIN ningun gap ni numero de articulo duplicado -- este documento no
necesito ningun parche puntual. Jerarquia Titulo > Capitulo > Seccion
detectada correctamente.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley que Previene y Combate la Discriminacion en el Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 203516 bytes,
# Last-Modified Fri, 15 Mar 2019 15:01:49 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0085.pdf?v=NA=="
PROCESSED_TXT = "data/processed/ley_discriminacion.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(2009, 4, 3)
FECHA_ULTIMA_REFORMA = date(2018, 1, 24)


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

        numericos = sorted({int(n.split("-")[0].split(" ")[0]) for n in numeros if n and n.split("-")[0].split(" ")[0].isdigit()})
        if numericos:
            gaps = [n for n in range(numericos[0], numericos[-1] + 1) if n not in numericos]
            print(f"rango numerico {numericos[0]}-{numericos[-1]}, gaps: {gaps if gaps else 'ninguno'}")

        document = Document(
            nombre=DOCUMENT_NOMBRE,
            tipo="ley",
            fecha_publicacion=FECHA_PUBLICACION,
            fecha_ultima_reforma=FECHA_ULTIMA_REFORMA,
            source_url=SOURCE_URL,
            area_derecho="derechos_humanos",
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
