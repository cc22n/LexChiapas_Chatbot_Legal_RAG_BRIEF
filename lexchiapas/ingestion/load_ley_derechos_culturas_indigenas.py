"""Script de ingesta puntual para la Ley de Derechos y Culturas Indigenas del
Estado de Chiapas (area_derecho=derechos_humanos).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="derechos_humanos" (no un valor nuevo) porque es el
mismo valor ya usado para la Ley Estatal para Prevenir y Sancionar la
Tortura (documents.id 8): esta ley reconoce y protege derechos colectivos
especificos (autonomia, usos y costumbres, acceso a la justicia, educacion
y salud interculturales) de los pueblos y comunidades indigenas, en la misma
linea tematica de derechos fundamentales. Se comparo contenido contra la Ley
Ambiental (unica coincidencia real encontrada al buscar la frase "pueblos
indigenas" en chunks ya cargados, documents.id 19) y se confirmo que NO es
duplicado: los chunks de la Ley Ambiental que mencionan pueblos indigenas
son sobre distribucion de beneficios de recursos naturales (Articulo 1,
fraccion IV) y consulta previa en materia ambiental (Articulo 47), temas
distintos del contenido sustantivo de esta ley (derechos culturales,
autonomia, acceso a la justicia).

Fechas leidas del propio PDF (encabezado, primeras lineas): "Ley publicada
en el Periodico Oficial numero 042 de fecha 29 de julio de 1999"
(publicacion original) y "ULTIMA REFORMA PUBLICADA MEDIANTE PERIODICO
OFICIAL NUMERO 113 DE FECHA 17 DE JUNIO DE 2026" (ultima reforma).

Hallazgos reales del chunking (chunk_legal_text sin parche): 70 chunks,
0 sin articulo_numero, rango 1-69, pero el PRIMER chunk (antes de cualquier
articulo real) traia articulo_numero="4o" en vez de ser preambulo ignorado.
Se investigo contra el texto fuente: en la seccion de CONSIDERANDOS (antes
del Articulo 1 real, linea 138 del .txt), hay una cita a otra ley ("hecho
reconocido en el\nart�culo 4�. de la Carta Magna Federal.") que pdfplumber
corta justo al inicio de una nueva linea de PDF -- el mismo patron de "cita
a mitad de oracion" que _is_midsentence_line ya sabe reconocer, EXCEPTO que
esa proteccion depende de haber un articulo activo (current_articulo no
None) para comparar contra la ultima linea de contenido; aqui la cita
aparece ANTES del primer articulo real, cuando current_articulo todavia es
None, asi que la funcion no tiene nada contra que comparar y siempre
devuelve False (no cita a mitad de oracion), dejando que "articulo 4o." se
reconozca como si fuera un encabezado real. El resultado sin parche: un
chunk fantasma con articulo_numero="4o" cuyo contenido es en realidad texto
del preambulo/considerandos (nunca citable, no es un articulo real de esta
ley) -- exactamente el tipo de mala cita que la regla de oro del dominio
legal prohibe. Se verifico que es un caso AISLADO (unica coincidencia de
ARTICULO_RE en todo el preambulo, antes del Articulo 1 real). Se corrige
uniendo la cita cortada a la linea anterior (quita el salto de linea que
hace que "articulo 4o." empiece su propia linea), sin alterar el texto legal
en si -- mismo tipo de parche ya usado en
load_codigo_procedimientos_penales.py para el caso del "478" citado dentro
de una lista.

Despues del parche: 69 chunks, 0 sin articulo_numero, rango 1-69 sin gaps,
sin numeros duplicados, primer chunk real es el Articulo 1.

Jerarquia: este documento no usa TITULO ni SECCION, solo CAPITULO I a X
(current_titulo queda None en todos los chunks, comportamiento correcto
para la estructura real de este documento, no un bug).
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de Derechos y Culturas Indigenas del Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 156059 bytes,
# Last-Modified Mon, 13 Jul 2026 21:31:48 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0026.pdf?v=Ng=="
PROCESSED_TXT = "data/processed/ley_derechos_culturas_indigenas.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(1999, 7, 29)
FECHA_ULTIMA_REFORMA = date(2026, 6, 17)

# Ver docstring del modulo: cita a mitad de oracion en el preambulo,
# cortada por pdfplumber al inicio de una nueva linea, ANTES del primer
# articulo real (por eso _is_midsentence_line no la protege).
_GAP_PREAMBULO_TYPO = "hecho reconocido en el\nartículo 4º. de la Carta Magna Federal."
_GAP_PREAMBULO_FIX = "hecho reconocido en el artículo 4º. de la Carta Magna Federal."


def _normalize_raw_text(raw_text: str) -> str:
    if _GAP_PREAMBULO_TYPO not in raw_text:
        return raw_text
    return raw_text.replace(_GAP_PREAMBULO_TYPO, _GAP_PREAMBULO_FIX)


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.nombre == DOCUMENT_NOMBRE).first()
        if existing is not None:
            print(f"Documento ya existe (id={existing.id}), no se vuelve a ingerir.")
            return

        with open(PROCESSED_TXT, encoding="utf-8") as f:
            raw_text = f.read()

        raw_text = _normalize_raw_text(raw_text)

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
