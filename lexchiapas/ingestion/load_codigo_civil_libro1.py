"""Script de ingesta puntual para el Codigo Civil para el Estado de Chiapas,
Libro Primero - De las Personas (area_derecho=civil).

El Codigo Civil completo (~3000 articulos, data/processed/codigo_civil.txt)
se esta cargando en 4 documentos separados por LIBRO, cada uno por un agente
distinto EN PARALELO. Este script carga SOLO el Libro Primero. NO toca nada
relacionado con Libro Segundo/Tercero/Cuarto.

El PDF y el texto ya fueron descargados/extraidos de antemano (no se repite
aqui). Fuente real:
https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/CODIGO%20CIVIL%20PARA%20EL%20ESTADO%20DE%20CHIAPAS.pdf

Corte del Libro Primero dentro de data/processed/codigo_civil.txt (lineas
0-indexed sobre splitlines()): [118:5256]. Verificado leyendo el archivo
directo: linea 118 es "LIBRO PRIMERO" (linea 119 "DE LAS PERSONAS"), y la
linea 5256 es "LIBRO SEGUNDO" (linea 5257 "DE LOS BIENES") -- esa linea y
todo lo que sigue NO es de este Libro. El slice [118:5256] excluye el indice
5256, asi que el Libro Primero termina en el ultimo articulo real (ART. 735,
"...PASAN A SUS HEREDEROS, SI AQUEL HA MUERTO.") sin arrastrar el
encabezado del Libro Segundo. Este script vuelve a verificar ese corte en
tiempo de ejecucion (primera linea == "LIBRO PRIMERO", ultima linea !=
"LIBRO SEGUNDO") antes de chunkear, para no depender ciegamente del numero
si el archivo fuente cambiara.

Nota sobre chunking (NO se modifico app/rag/chunker.py):
Se valido chunk_legal_text (el chunker COMPARTIDO, sin ninguna
reimplementacion local) directamente contra el texto real de este Libro
Primero: 757 chunks, 0 sin articulo_numero, 0 numeros de articulo
duplicados. Las lineas que citan "CAPITULO X"/"TITULO X" a mitad de oracion
dentro de este documento (ej. "...LAS CUENTAS A LAS QUE SE REFIERE AL\\n
CAPITULO XI DE ESTE TITULO, SERA OBLIGATORIA...") ya las filtra
correctamente la heuristica compartida de "cita a mitad de oracion"
(_is_midsentence_line en app/rag/chunker.py, documentada ahi mismo). No se
encontro ningun bug nuevo en esta porcion del documento, asi que no hubo
necesidad de tocar el modulo compartido.

Idempotente: si el documento ya existe (por nombre exacto), no vuelve a
insertarlo ni a generar embeddings de nuevo.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = (
    "Codigo Civil para el Estado de Chiapas - Libro Primero (De las Personas)"
)
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/CODIGO%20CIVIL%20PARA%20EL%20ESTADO%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/codigo_civil.txt"

# Leido del propio texto extraido (lineas 0-6): "Codigo publicado en el
# Alcance al Periodico Oficial Estado de Chiapas, el 2 de febrero de 1938."
# y "ULTIMA REFORMA PUBLICADA EN EL PERIODICO OFICIAL: 23 DE ENERO DE 2019."
FECHA_PUBLICACION = date(1938, 2, 2)
FECHA_ULTIMA_REFORMA = date(2019, 1, 23)

# Corte del Libro Primero dentro del texto completo, ver docstring del modulo.
LIBRO_PRIMERO_START_LINE = 118
LIBRO_PRIMERO_END_LINE = 5256  # exclusivo


def load_libro_primero_text() -> str:
    with open(PROCESSED_TXT, encoding="utf-8") as f:
        lines = f.read().splitlines()

    portion = lines[LIBRO_PRIMERO_START_LINE:LIBRO_PRIMERO_END_LINE]

    if not portion or portion[0].strip().upper() != "LIBRO PRIMERO":
        raise RuntimeError(
            f"Corte invalido: la primera linea de la porcion es "
            f"{portion[0]!r}, se esperaba 'LIBRO PRIMERO'. Revisar offsets."
        )
    if portion[-1].strip().upper() == "LIBRO SEGUNDO":
        raise RuntimeError(
            "Corte invalido: la ultima linea de la porcion es 'LIBRO "
            "SEGUNDO', deberia estar excluida. Revisar offsets."
        )

    return "\n".join(portion)


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.nombre == DOCUMENT_NOMBRE).first()
        if existing is not None:
            print(f"Documento ya existe (id={existing.id}), no se vuelve a ingerir.")
            return

        raw_text = load_libro_primero_text()
        print(f"Primera linea de la porcion: {raw_text.splitlines()[0]!r}")
        print(f"Ultima linea de la porcion: {raw_text.splitlines()[-1]!r}")

        legal_chunks = chunk_legal_text(raw_text, document_nombre=DOCUMENT_NOMBRE)
        print(f"chunk_legal_text produjo {len(legal_chunks)} chunks")

        sin_articulo = sum(1 for c in legal_chunks if c.articulo_numero is None)
        print(f"chunks sin articulo_numero: {sin_articulo}")

        numeros = [c.articulo_numero for c in legal_chunks]
        duplicados = {n for n in numeros if numeros.count(n) > 1}
        print(f"numeros de articulo duplicados: {sorted(duplicados) if duplicados else 'ninguno'}")

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
