"""Script de ingesta puntual para la Ley de Instituciones y Procedimientos
Electorales del Estado de Chiapas (area_derecho=electoral).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se introduce el valor NUEVO de area_derecho="electoral" (no existia en la
tabla documents hasta esta ingesta) porque ninguna categoria ya en uso
encaja: esta es la unica ley de materia electoral en el corpus hasta ahora
(organizacion de elecciones, partidos politicos, candidaturas independientes,
Instituto de Elecciones y Participacion Ciudadana). No se comparo contra
ningun documento activo con contenido solapado real (busqueda de "candidato
independiente" en chunks existentes: cero resultados).

Fechas leidas del propio PDF (encabezado, primeras lineas): "PUBLICADA EN EL
PERIODICO NUMERO 305, DE FECHA 22 DE SEPTIEMBRE DE 2023" (publicacion
original) y "ULTIMA REFORMA PUBLICADA MEDIANTE PERIODICO OFICIAL NUMERO 115
DE FECHA 01 DE JULIO DEL ANO 2026" (ultima reforma).

Hallazgos reales del chunking (chunk_legal_text sin parche): 344 chunks,
0 sin articulo_numero, rango 1-345, DOS gaps reales (128, 147) y un chunk
FANTASMA extra (el primero, con articulo_numero="2o") que en realidad es
preambulo. Se investigaron los tres contra el texto fuente antes de decidir
un parche puntual:

1. Chunk fantasma "2o": este documento tiene una seccion muy larga de
   ANTECEDENTES (justificacion legislativa) ANTES del Articulo 1 real (que
   empieza hasta la linea 1452 del .txt procesado). Dentro de esa seccion,
   el legislador transcribe TEXTUALMENTE el Articulo 2 completo de la
   Constitucion Politica de los Estados Unidos Mexicanos (sobre pueblos
   indigenas) como cita de referencia ("...es del tenor siguiente.\n
   Articulo 2o. La Nacion Mexicana es unica e indivisible..."), y esa cita
   arranca su propia linea de PDF justo despues de dos puntos implicitos.
   Como esto ocurre ANTES del primer articulo real de ESTA ley,
   current_articulo todavia es None en ese punto, asi que
   _is_midsentence_line (que depende de comparar contra el ultimo articulo
   ACTIVO) nunca puede proteger este caso -- el chunker trata la cita
   completa como si fuera el Articulo 2 real de esta ley, y absorbe TODO el
   contenido siguiente (casi 1000 lineas de narrativa de antecedentes) como
   si fuera contenido de ese articulo fantasma, hasta que el Articulo 1 REAL
   aparece y lo corta. Esto es exactamente el tipo de mala cita que la
   regla de oro del dominio legal prohibe (contenido no normativo atribuido
   a un numero de articulo real). Se verifico que es un caso AISLADO (ningun
   otro "ARTICULO N" real matchea dentro de ese bloque de antecedentes). Se
   corrige uniendo la linea del encabezado de la cita a la linea anterior
   (evita que "Articulo 2o." empiece su propia linea), de forma que el
   bloque completo de antecedentes vuelva a tratarse como preambulo
   (ignorado, sin articulo_numero, tal como ya documenta el docstring de
   chunk_legal_text).
2. Gap del Articulo 128: mismo patron ya visto varias veces en este lote --
   la ultima linea de contenido del Articulo 127 ("...con excepcion de lo
   relativo al porcentaje requerido de apoyo ciudadano") no cierra con punto
   final antes del encabezado real de "Articulo 128.". Se corrige agregando
   el punto que falta.
3. Gap del Articulo 147: variante NUEVA del typo de separador, distinta de
   las vistas antes en este lote: el PDF escribe "Articulo. 147" (punto
   pegado a la palabra "Articulo", ANTES del numero, en vez de "Articulo
   147." con el punto despues del numero). ARTICULO_RE exige que el prefijo
   sea "ARTICULOS?" (sin punto) o la abreviatura "ART." (con punto pero solo
   3 letras); "Articulo." (8 letras + punto) no calza con ninguna de las dos
   alternativas, asi que la linea no matchea en absoluto y el Articulo 147
   completo se funde como contenido del Articulo 146 anterior. Se verifico
   que es un caso AISLADO (unica coincidencia de "Articulo." seguido de
   numero en todo el documento). Se corrige normalizando a "Articulo 147."
   (formato estandar del resto del documento).

Despues de los tres parches: 345 chunks, 0 sin articulo_numero, rango 1-345
sin gaps, sin numeros duplicados, primer chunk real es el Articulo 1.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de Instituciones y Procedimientos Electorales del Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 1859405 bytes,
# Last-Modified Tue, 14 Jul 2026 21:30:32 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0145.pdf?v=NQ=="
PROCESSED_TXT = "data/processed/ley_electoral.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(2023, 9, 22)
FECHA_ULTIMA_REFORMA = date(2026, 7, 1)

# Ver docstring del modulo: tres typos/casos puntuales de este PDF fuente.
_PREAMBLE_TYPO = (
    "Unidos Mexicanos es del tenor siguiente.\n"
    "Artículo 2º. La Nación Mexicana es única e indivisible."
)
_PREAMBLE_FIX = (
    "Unidos Mexicanos es del tenor siguiente. "
    "Artículo 2º. La Nación Mexicana es única e indivisible."
)
_GAP_128_TYPO = (
    "excepción de lo relativo al porcentaje requerido de apoyo ciudadano\n"
    "Artículo 128."
)
_GAP_128_FIX = (
    "excepción de lo relativo al porcentaje requerido de apoyo ciudadano.\n"
    "Artículo 128."
)
_GAP_147_TYPO = "Artículo. 147"
_GAP_147_FIX = "Artículo 147."


def _normalize_raw_text(raw_text: str) -> str:
    if _PREAMBLE_TYPO in raw_text:
        raw_text = raw_text.replace(_PREAMBLE_TYPO, _PREAMBLE_FIX)
    if _GAP_128_TYPO in raw_text:
        raw_text = raw_text.replace(_GAP_128_TYPO, _GAP_128_FIX)
    if _GAP_147_TYPO in raw_text:
        raw_text = raw_text.replace(_GAP_147_TYPO, _GAP_147_FIX)
    return raw_text


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
            area_derecho="electoral",
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
