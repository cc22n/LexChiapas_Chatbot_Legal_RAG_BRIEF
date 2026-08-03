"""Script de ingesta puntual para la Ley de Desarrollo Forestal Sustentable
para el Estado de Chiapas (area_derecho=ambiental).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="ambiental" (no un valor nuevo) porque es el mismo
valor ya usado para la Ley Ambiental para el Estado de Chiapas (documents.id
19) y para la Ley de Aguas (cargada en esta misma tanda). Motivo de esta
ingesta (ver instrucciones del lote): la Ley Ambiental solo cubre la tala de
arboles de forma tangencial; esta ley es la que realmente regula el
aprovechamiento y proteccion forestal (permisos de aprovechamiento,
reforestacion, incendios forestales, sanciones por tala ilegal). Se
verifico que no es duplicado de ningun documento ya cargado (busqueda de
"aprovechamiento forestal" en chunks existentes: unica coincidencia es un
articulo del Codigo Penal que tipifica el delito de tala ilegal como tal,
no el contenido regulatorio/administrativo completo que trae esta ley).

Fechas leidas del propio PDF (encabezado, primeras lineas): "LEY DE NUEVA
CREACION PUBLICADA MEDIANTE PERIODICO OFICIAL NUMERO 257. TOMO III DE FECHA
14 DE DICIEMBRE DE 2022" (publicacion original) y "ULTIMA REFORMA PUBLICADA
MEDIANTE PERIODICO OFICIAL NUMERO 089 DE FECHA 04 DE FEBRERO DEL 2026"
(ultima reforma).

Hallazgos reales del chunking: 119 chunks, 0 sin articulo_numero, rango
1-119, SIN ningun gap ni numero de articulo duplicado -- este documento no
necesito ningun parche puntual. Jerarquia Titulo > Capitulo detectada
correctamente (encabezados simples "Titulo Primero", "Capitulo Unico", sin
el problema de punto final ya corregido en chunker.py para el Codigo de
Procedimientos Civiles).
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de Desarrollo Forestal Sustentable para el Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 521914 bytes,
# Last-Modified Tue, 10 Mar 2026 21:37:35 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0028.pdf?v=NQ=="
PROCESSED_TXT = "data/processed/ley_forestal.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(2022, 12, 14)
FECHA_ULTIMA_REFORMA = date(2026, 2, 4)


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
            area_derecho="ambiental",
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
