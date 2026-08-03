"""Script de ingesta puntual para la Ley de Proteccion para la Fauna en el
Estado de Chiapas (area_derecho=ambiental).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="ambiental" (no un valor nuevo) porque es el mismo
valor ya usado para la Ley Ambiental (documents.id 19), la Ley de Aguas y la
Ley de Desarrollo Forestal Sustentable (ambas cargadas en esta misma tanda).
Se comparo contenido contra la Ley Ambiental (busqueda de "fauna silvestre"
en chunks existentes) y se confirmo que NO es duplicado: los chunks de la
Ley Ambiental que mencionan fauna silvestre son sobre ordenamiento
ecologico, convenios de coordinacion federal-estatal y biodiversidad en
general, mientras que esta ley regula especificamente el bienestar/trato de
los animales (maltrato, cautiverio, espectaculos, zoologicos, permisos de
caza) -- contenido sustantivo distinto.

Fechas leidas del propio PDF (encabezado, primeras lineas): "* SE EXPIDE EL
27 DE JUNIO DE 1995, PUBLICADO BAJO DECRETO #183, MEDIANTE PERIODICO OFICIAL
#043 DE FECHA 5 DE JULIO DE 1995" (se usa la fecha de publicacion en el
Periodico Oficial, 5 de julio de 1995, siguiendo la misma convencion usada
en los demas scripts de este lote) y "(ULTIMA REFORMA PUBLICADA MEDIANTE
DECRETO NUMERO 487, PUBLICADA EN EL PERIODICO OFICIAL No. 107 TERCERA
SECCION DE FECHA 15 DE MAYO DE 2014)" (ultima reforma).

Hallazgos reales del chunking: 95 chunks, 0 sin articulo_numero, rango
1-95, SIN ningun gap ni numero de articulo duplicado -- este documento no
necesito ningun parche puntual. Esta ley no usa TITULO ni SECCION, solo
CAPITULO I a XII (current_titulo queda None en todos los chunks,
comportamiento correcto para la estructura real de este documento).
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de Proteccion para la Fauna en el Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 103792 bytes,
# Last-Modified Fri, 15 Mar 2019 15:01:26 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = (
    "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/"
    "ley%20de%20proteccion%20para%20la%20fauna%20en%20el%20estado%20de%20"
    "chiapas.pdf?v=Mw=="
)
PROCESSED_TXT = "data/processed/ley_fauna.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(1995, 7, 5)
FECHA_ULTIMA_REFORMA = date(2014, 5, 15)


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
