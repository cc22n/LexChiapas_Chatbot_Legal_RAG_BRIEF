"""Script de ingesta puntual para la Ley de Aguas para el Estado de Chiapas
(area_derecho=ambiental).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="ambiental" (no un valor nuevo) porque es el mismo
valor ya usado para la Ley Ambiental para el Estado de Chiapas (documents.id
19): esta ley regula el recurso hidrico (organismos operadores de agua
potable, alcantarillado, saneamiento, concesiones) como un recurso natural,
en la misma linea tematica que la Ley Ambiental. Se comparo contenido contra
esa ley (busqueda de frases distintivas de esta nueva ley, ej. "INSTITUTO
ESTATAL DEL AGUA", en los chunks ya cargados) y no se encontro overlap real.

Fechas leidas del propio PDF (encabezado, primeras lineas): "Ley publicada en
el Periodico Oficial del Estado Libre y Soberano de Chiapas, el 07 DE JULIO
DEL 2004" (publicacion original) y "ULTIMA REFORMA PUBLICADA EN EL PERIODICO
OFICIAL DEL ESTADO NO. 073, DE FECHA 11 DE DICIEMBRE DE 2013" (ultima
reforma).

Hallazgos reales del chunking: 212 chunks, 0 sin articulo_numero, rango 1-210
(mas dos articulos "1o"/"2o" con indicador ordinal, ver mas abajo), SIN
ningun gap ni numero de articulo duplicado -- este documento no necesito
ningun parche puntual. Se verifico especificamente un caso de cita a mitad de
oracion cortada por pdfplumber ("...EN LOS TERMINOS DEL\nARTICULO 59." dentro
de la fraccion XII del Articulo 3, definiciones) para confirmar que
_is_midsentence_line ya la maneja correctamente (la linea anterior no cierra
en puntuacion, asi que "ARTICULO 59." ahi se trata como continuacion del
Articulo 3 activo, no como un encabezado nuevo) -- no hizo falta ningun
parche para ese caso.

Los primeros dos articulos usan el indicador ordinal en superindice
("ARTICULO 1o.-", "ARTICULO 2o.-") que ARTICULO_RE ya sabe normalizar (ver
comentario junto a ARTICULO_RE en app/rag/chunker.py, mismo caso que la Ley
de Amnistia), por eso su articulo_numero queda como "1o"/"2o" en vez de
"1"/"2" -- comportamiento esperado, no un bug.

La jerarquia Titulo > Capitulo se detecto correctamente (encabezados simples
tipo "TITULO PRIMERO", "CAPITULO UNICO", sin el problema de punto final ya
corregido en chunker.py para el Codigo de Procedimientos Civiles). Esta ley
no usa SECCION.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de Aguas para el Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 468966 bytes,
# Last-Modified Fri, 15 Mar 2019 15:01:35 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = (
    "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/"
    "ley%20de%20aguas%20para%20el%20estado%20de%20chiapas.pdf?v=Mw=="
)
PROCESSED_TXT = "data/processed/ley_aguas.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(2004, 7, 7)
FECHA_ULTIMA_REFORMA = date(2013, 12, 11)


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

        numericos = sorted({int(n.split("-")[0].split(" ")[0].rstrip("oO")) for n in numeros if n and n.split("-")[0].split(" ")[0].rstrip("oO").isdigit()})
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
