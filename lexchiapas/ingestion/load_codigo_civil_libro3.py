"""Script de ingesta puntual para el Codigo Civil para el Estado de Chiapas,
Libro Tercero - De las Sucesiones (area_derecho=civil).

El Codigo Civil completo (~3000 articulos, data/processed/codigo_civil.txt)
se esta cargando en 4 documentos separados por LIBRO, cada uno por un agente
distinto EN PARALELO. Este script carga SOLO el Libro Tercero. NO toca nada
relacionado con Libro Primero/Segundo/Cuarto.

El PDF y el texto ya fueron descargados/extraidos de antemano (no se repite
aqui). Fuente real:
https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/CODIGO%20CIVIL%20PARA%20EL%20ESTADO%20DE%20CHIAPAS.pdf

Corte del Libro Tercero dentro de data/processed/codigo_civil.txt (lineas
0-indexed sobre splitlines()): [8137:10487]. Verificado leyendo el archivo
directo: la linea 8137 es el encabezado "L I B R O   T E R C E R O" con las
letras espaciadas (asi extrae pdfplumber este encabezado en particular, igual
que ya pasaba con "T R A N S I T O R I O" en otras leyes; la linea 8138 es
"DE LAS SUCESIONES"), y la linea 10487 es "LIBRO CUARTO" (linea 10488 "DE LAS
OBLIGACIONES") -- esa linea y todo lo que sigue NO es de este Libro. El slice
[8137:10487] excluye el indice 10487, asi que el Libro Tercero termina en el
ultimo articulo real (ART. 1765, "...SE OBSERVARAN LAS DISPOSICIONES
CONTENIDAS EN ESTE TITULO.") sin arrastrar el encabezado del Libro Cuarto.
Este script vuelve a verificar ese corte en tiempo de ejecucion (primera
linea contiene las letras espaciadas de "LIBRO TERCERO", ultima linea != la
del encabezado "LIBRO CUARTO") antes de chunkear, para no depender
ciegamente del numero si el archivo fuente cambiara.

Nota sobre el encabezado espaciado "L I B R O   T E R C E R O":
No matchea TITULO_RE ni TRANSITORIO_RE (ni ningun otro limite reconocido por
el chunker), asi que se trata igual que el preambulo antes del primer
ARTICULO real en cualquier otra ley: se ignora para efectos de chunk (no hay
articulo activo todavia cuando aparece esta linea, ver chunk_legal_text). Se
verifico que esto es correcto (no se cuela dentro de ningun chunk real, ver
docstring de main() para el chequeo).

Nota sobre chunking (NO se modifico app/rag/chunker.py):
Se valido chunk_legal_text (el chunker COMPARTIDO, sin ninguna
reimplementacion local) directamente contra el texto real de este Libro
Tercero: 493 chunks, 0 sin articulo_numero, 0 numeros de articulo duplicados.
No se encontro ningun bug nuevo en esta porcion del documento, asi que no
hubo necesidad de tocar el modulo compartido.

Idempotente: si el documento ya existe (por nombre exacto), no vuelve a
insertarlo ni a generar embeddings de nuevo.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = (
    "Codigo Civil para el Estado de Chiapas - Libro Tercero (De las Sucesiones)"
)
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/CODIGO%20CIVIL%20PARA%20EL%20ESTADO%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/codigo_civil.txt"

# Leido del propio texto extraido (lineas 0-6): "Codigo publicado en el
# Alcance al Periodico Oficial Estado de Chiapas, el 2 de febrero de 1938."
# y "ULTIMA REFORMA PUBLICADA EN EL PERIODICO OFICIAL: 23 DE ENERO DE 2019."
# (mismas fechas que Libro Primero: es el mismo codigo completo, solo se
# parte el documento por Libro para efectos de chunking/ingesta).
FECHA_PUBLICACION = date(1938, 2, 2)
FECHA_ULTIMA_REFORMA = date(2019, 1, 23)

# Corte del Libro Tercero dentro del texto completo, ver docstring del modulo.
LIBRO_TERCERO_START_LINE = 8137
LIBRO_TERCERO_END_LINE = 10487  # exclusivo

# El encabezado real tiene las letras espaciadas por el PDF ("L I B R O   T E
# R C E R O"), asi que se compara normalizando espacios internos en vez de un
# match exacto de string.
_EXPECTED_FIRST_LINE_COMPACT = "LIBROTERCERO"
_FORBIDDEN_LAST_LINE_COMPACT = "LIBROCUARTO"


def load_libro_tercero_text() -> str:
    with open(PROCESSED_TXT, encoding="utf-8") as f:
        lines = f.read().splitlines()

    portion = lines[LIBRO_TERCERO_START_LINE:LIBRO_TERCERO_END_LINE]

    first_compact = portion[0].strip().upper().replace(" ", "") if portion else ""
    if not portion or first_compact != _EXPECTED_FIRST_LINE_COMPACT:
        first_line_repr = repr(portion[0]) if portion else "None"
        raise RuntimeError(
            f"Corte invalido: la primera linea de la porcion es "
            f"{first_line_repr}, se esperaba el "
            f"encabezado (con o sin letras espaciadas) de 'LIBRO TERCERO'. "
            f"Revisar offsets."
        )
    last_compact = portion[-1].strip().upper().replace(" ", "")
    if last_compact == _FORBIDDEN_LAST_LINE_COMPACT:
        raise RuntimeError(
            "Corte invalido: la ultima linea de la porcion es 'LIBRO "
            "CUARTO', deberia estar excluida. Revisar offsets."
        )

    return "\n".join(portion)


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.nombre == DOCUMENT_NOMBRE).first()
        if existing is not None:
            print(f"Documento ya existe (id={existing.id}), no se vuelve a ingerir.")
            return

        raw_text = load_libro_tercero_text()
        print(f"Primera linea de la porcion: {raw_text.splitlines()[0]!r}")
        print(f"Ultima linea de la porcion: {raw_text.splitlines()[-1]!r}")

        legal_chunks = chunk_legal_text(raw_text, document_nombre=DOCUMENT_NOMBRE)
        print(f"chunk_legal_text produjo {len(legal_chunks)} chunks")

        sin_articulo = sum(1 for c in legal_chunks if c.articulo_numero is None)
        print(f"chunks sin articulo_numero: {sin_articulo}")

        numeros = [c.articulo_numero for c in legal_chunks]
        duplicados = {n for n in numeros if numeros.count(n) > 1}
        print(f"numeros de articulo duplicados: {sorted(duplicados) if duplicados else 'ninguno'}")

        # Chequeo adicional: el encabezado espaciado "L I B R O   T E R C E R
        # O" / "DE LAS SUCESIONES" no debe haberse colado dentro de ningun
        # chunk real (deberia quedar descartado como preambulo, ver docstring
        # del modulo).
        leaked = [c for c in legal_chunks if "L I B R O" in c.content or "DE LAS SUCESIONES" in c.content]
        print(f"chunks con posible fuga del encabezado del Libro: {len(leaked)}")

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
