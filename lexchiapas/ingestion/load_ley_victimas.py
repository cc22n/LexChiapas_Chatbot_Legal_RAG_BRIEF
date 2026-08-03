"""Script de ingesta puntual para la Ley de Victimas para el Estado de
Chiapas (area_derecho=derechos_humanos).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="derechos_humanos" (no un valor nuevo) porque es el
mismo valor ya usado para la Ley Estatal para Prevenir y Sancionar la
Tortura (documents.id 8), la Ley de Derechos y Culturas Indigenas y la Ley
en Materia de Desaparicion de Personas (ambas cargadas en esta misma
tanda): esta ley reconoce y regula los derechos de las victimas de delitos
y de violaciones a derechos humanos (reparacion integral, comision estatal
de atencion a victimas, registro de victimas). Se comparo contenido contra
otros documentos que mencionan "reparacion integral del dano" (Ley de
Derechos de NNA id 11, Codigo Penal id 24, Codigo de Procedimientos Penales
id 30) y se confirmo que NO es duplicado: son referencias cruzadas o
menciones puntuales (la Ley de NNA de hecho remite expresamente a "la Ley
de Victimas para el Estado de Chiapas" en su Articulo 54, confirmando que
esta ley llena un hueco de cita real que ya existia en el corpus).

Fechas leidas del propio PDF (encabezado, primeras lineas): "TEXTO DE NUEVA
CREACION PUBLICADA MEDIANTE PERIODICO OFICIAL, NUMERO 344 DE FECHA 01 DE
MAYO DE 2024" -- ley de creacion reciente, sin reformas posteriores todavia
(no hay linea de "ULTIMA REFORMA" en el encabezado del PDF), por lo que
fecha_ultima_reforma se deja en None en vez de repetir la fecha de
publicacion.

Hallazgos reales del chunking: 172 chunks, 0 sin articulo_numero, rango
1-172, SIN ningun gap ni numero de articulo duplicado -- este documento no
necesito ningun parche puntual. Jerarquia Titulo > Capitulo > Seccion
detectada correctamente.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de Victimas para el Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 414585 bytes,
# Last-Modified Mon, 20 May 2024 20:46:13 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso). NOTA: en el
# listado de list_available_laws() el nombre trae doble espacio ("LEY DE
# VICTIMAS" -> "LEY DE  VICTIMAS PARA EL ESTADO DE CHIAPAS"), se normaliza
# aqui al nombre canonico sin doble espacio.
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0080.pdf?v=Ng=="
PROCESSED_TXT = "data/processed/ley_victimas.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(2024, 5, 1)
FECHA_ULTIMA_REFORMA = None


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
