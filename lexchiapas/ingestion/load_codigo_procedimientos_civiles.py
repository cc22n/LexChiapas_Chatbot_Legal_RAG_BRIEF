"""Script de ingesta puntual para el Codigo de Procedimientos Civiles para el
Estado de Chiapas (area_derecho=civil).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="civil" (no un valor nuevo) porque este codigo es el
complemento procesal del Codigo Civil para el Estado de Chiapas (ya cargado,
documents.id 20-23) y de la Ley del Notariado (tambien "civil"): juntos
cubren el derecho sustantivo y el proceso civil completo. No se comparo
contra ningun documento ya activo con contenido solapado -- este es un
codigo PROCESAL (juicios, recursos, sucesiones testamentarias/intestadas via
tramite judicial/notarial), distinto en alcance del Codigo Civil (derecho
sustantivo) y del Codigo de Atencion a la Familia.

Fechas leidas del propio PDF (encabezado, primeras lineas): "Codigo
publicado en Alcance al Periodico Oficial del Estado de Chiapas, de 2 de
febrero de 1938" (fecha de publicacion original) y "ULTIMA REFORMA
PUBLICADA MEDIANTE PERIODICO OFICIAL DEL ESTADO NUMERO 012-4a. SECCION DE
FECHA 23 DE ENERO DE 2019" (ultima reforma).

Hallazgos reales del chunking (chunk_legal_text sin parche): 1030 chunks,
0 sin articulo_numero, rango numerico 1-1009, UN gap real (846) y UN
numero de articulo duplicado real (280, dos articulos distintos colapsados
bajo el mismo numero). Se investigaron ambos contra el texto fuente antes
de decidir un parche puntual (no se asumio bug generico del chunker):

1. Gap del Articulo 846: la ultima linea de contenido del Articulo 845
   ("...DE LO QUE SE DEJARA CONSTANCIA EN EL INSTRUMENTO") no cierra con
   punto final antes del encabezado real de "ART. 846.-" -- mismo tipo de
   typo puntual del PDF fuente ya documentado en load_ley_discapacidad.py
   (Articulo 47) y load_ley_transparencia.py (Articulo 72): sin punto
   final, _is_midsentence_line trata el encabezado de 846 como cita a
   mitad de oracion y lo fusiona como contenido de 845, haciendo
   desaparecer el Articulo 846 completo del chunking.
2. Duplicado del "280": el PDF fuente escribe el articulo adicionado como
   "ART. 280-BIS.-" (sufijo latino BIS pegado al numero por un GUION, sin
   espacio). ARTICULO_RE (app/rag/chunker.py) solo reconoce un sufijo de
   UNA letra tras guion (patron "278-A"/"278-B" del Codigo Fiscal, ej.
   articulos adicionados con letra), o un sufijo de palabra completa
   separado por ESPACIO (patron "117 BIS" de la Ley de Salud). "280-BIS"
   no calza en ninguno de los dos: el regex intenta el sufijo de una letra
   tras guion, consume solo la "B" de "BIS" y falla a completar el match
   final, por lo que retrocede (backtrack) y termina matcheando unicamente
   el guion suelto como separador de cierre -- el resultado es que este
   articulo se etiqueta erroneamente con articulo_numero="280" (el mismo
   numero que el Articulo 280 real, dos parrafos antes), y su contenido
   real ("...PODRA LA PARTE ACTORA PEDIR QUE SE SEÑALE FECHA Y HORA PARA
   LA AUDIENCIA DE CONCILIACION...", sobre conciliacion procesal) queda
   atribuido con una cita incorrecta -- exactamente el tipo de mala cita
   que la regla de oro del dominio legal prohibe. Se verifico que es un
   caso AISLADO: es el UNICO articulo en todo el documento que usa un
   sufijo de mas de una letra pegado por guion sin espacio (regex de
   verificacion "ART\\.\\s*(\\d+)-([A-Z]{2,})" sobre las 1030+ lineas de
   encabezado, una sola coincidencia). Se corrige aqui normalizando
   "ART. 280-BIS.-" a "ART. 280 BIS.-" (guion por espacio, mismo formato
   ya soportado por el sufijo de palabra completa), no en la heuristica
   compartida de chunker.py -- es un typo puntual de formato de ESTE PDF,
   no un patron estructural nuevo (el resto del documento sigue el patron
   ya conocido "278-A"/"278-B" de una sola letra sin problema).

Despues de ambos parches: 1031 chunks, 0 sin articulo_numero, rango 1-1009
sin gaps, sin numeros duplicados.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Codigo de Procedimientos Civiles para el Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 1469840 bytes,
# Last-Modified Fri, 15 Mar 2019 15:02:03 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0009.pdf?v=OQ=="
PROCESSED_TXT = "data/processed/codigo_procedimientos_civiles.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(1938, 2, 2)
FECHA_ULTIMA_REFORMA = date(2019, 1, 23)

# Ver docstring del modulo: dos typos puntuales de este PDF fuente.
_GAP_846_TYPO = "QUE SE DEJARA CONSTANCIA EN EL INSTRUMENTO\nART. 846.-"
_GAP_846_FIX = "QUE SE DEJARA CONSTANCIA EN EL INSTRUMENTO.\nART. 846.-"
_DUP_280_TYPO = "ART. 280-BIS.-"
_DUP_280_FIX = "ART. 280 BIS.-"


def _normalize_raw_text(raw_text: str) -> str:
    if _GAP_846_TYPO in raw_text:
        raw_text = raw_text.replace(_GAP_846_TYPO, _GAP_846_FIX)
    if _DUP_280_TYPO in raw_text:
        raw_text = raw_text.replace(_DUP_280_TYPO, _DUP_280_FIX)
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
