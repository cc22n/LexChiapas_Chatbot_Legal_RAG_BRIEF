"""Script de ingesta puntual para el Codigo Civil para el Estado de Chiapas,
Libro Cuarto - De las Obligaciones (area_derecho=civil).

El Codigo Civil completo (~3000 articulos, data/processed/codigo_civil.txt)
se esta cargando en 4 documentos separados por LIBRO, cada uno por un agente
distinto EN PARALELO. Este script carga SOLO el Libro Cuarto (la porcion mas
grande de las 4: contratos, obligaciones en general, y responsabilidad
civil). NO toca nada relacionado con Libro Primero/Segundo/Tercero.

El PDF y el texto ya fueron descargados/extraidos de antemano (no se repite
aqui). Fuente real:
https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/CODIGO%20CIVIL%20PARA%20EL%20ESTADO%20DE%20CHIAPAS.pdf

Corte del Libro Cuarto dentro de data/processed/codigo_civil.txt (lineas
0-indexed sobre splitlines()): [10487:] (hasta el final del archivo, no hay
Libro Quinto). Verificado leyendo el archivo directo: la linea 10487 es
"LIBRO CUARTO" (linea 10488 "DE LAS OBLIGACIONES"), y el archivo completo
tiene 17983 lineas (ultimo indice valido 17982), asi que el slice [10487:]
llega hasta el final real del documento, incluyendo la seccion de
"ARTICULOS TRANSITORIOS" que aparece cerca del final (ver nota sobre
chunker.py mas abajo). Este script vuelve a verificar ese corte en tiempo de
ejecucion (primera linea == "LIBRO CUARTO") antes de chunkear, para no
depender ciegamente del numero si el archivo fuente cambiara.

Nota sobre chunking -- SI se modifico app/rag/chunker.py (bug nuevo real,
no un typo puntual de este documento):
Se encontro un bug real en el chunker compartido al validar chunk_legal_text
contra el texto real de este Libro Cuarto. El encabezado real de la seccion
final de este documento es "ARTICULOS TRANSITORIOS" (dos palabras), no
"TRANSITORIOS" a secas como TRANSITORIO_RE original exigia, asi que no se
reconocia como limite. Peor aun: los transitorios del decreto original de
1938 estan numerados con el mismo formato NUMERICO que un articulo normativo
real ("ART. 1.- ESTE CODIGO ENTRARA EN VIGOR...", "ART. 2.-", ..., hasta
"ART. 7.-"), a diferencia de la convencion mas comun de ordinales en palabra
("PRIMERO.-", "SEGUNDO.-") que ARTICULO_RE nunca matchea. Sin arreglo, esto
generaba 7 chunks fantasma con articulo_numero "1" al "7" atribuidos a Libro
Cuarto -- una mala cita, porque esos numeros no son articulos reales de este
Libro, son clausulas transitorias del decreto fundacional de todo el Codigo
(y el documento sigue transcribiendo, tras ese decreto original, los
transitorios de cada decreto de reforma posterior hasta el final del
archivo). Se corrigio en dos partes, ambas en app/rag/chunker.py (nunca en
una copia local), con test de regresion nuevo en tests/test_chunker.py
(pytest tests/ corrido despues, 20/20 pasan):
  1. TRANSITORIO_RE ahora acepta un prefijo opcional "ARTICULO(S) " antes de
     "TRANSITORIO(S)".
  2. chunk_legal_text ahora tiene un estado `past_transitorios`: una vez
     cruzado ese limite, NINGUNA linea posterior (sea TITULO/CAPITULO/
     SECCION/ARTICULO o no, sea cual sea su formato de numeracion) puede
     volver a abrir un chunk nuevo. Esto es seguro para cualquier documento
     legal mexicano porque TRANSITORIOS es siempre la ultima seccion.
Esta correccion es generalizable (protege a cualquier ley que numere sus
transitorios con formato numerico o use el encabezado plural), no es
especifica de este documento.

Resultado tras el arreglo: 1253 chunks (bajo de 1259 antes del arreglo, los
6 que bajaron son exactamente los chunks fantasma "1" a "6" -- el septimo,
"7", nunca se conto porque quedaba sin cerrar/flush hasta el siguiente
limite real, que ya no existe tras la correccion), 0 sin articulo_numero, 0
numeros de articulo duplicados. El ultimo articulo real es el 3016 ("LAS
INSCRIPCIONES PREVENTIVAS, SE CANCELARAN..."), confirmado contra el texto
fuente.

Idempotente: si el documento ya existe (por nombre exacto), no vuelve a
insertarlo ni a generar embeddings de nuevo.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = (
    "Codigo Civil para el Estado de Chiapas - Libro Cuarto (De las Obligaciones)"
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

# Corte del Libro Cuarto dentro del texto completo, ver docstring del modulo.
# No hay Libro Quinto: este Libro llega hasta el final real del archivo.
LIBRO_CUARTO_START_LINE = 10487


def load_libro_cuarto_text() -> str:
    with open(PROCESSED_TXT, encoding="utf-8") as f:
        lines = f.read().splitlines()

    portion = lines[LIBRO_CUARTO_START_LINE:]

    if not portion or portion[0].strip().upper() != "LIBRO CUARTO":
        raise RuntimeError(
            f"Corte invalido: la primera linea de la porcion es "
            f"{portion[0]!r}, se esperaba 'LIBRO CUARTO'. Revisar offsets."
        )

    return "\n".join(portion)


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.nombre == DOCUMENT_NOMBRE).first()
        if existing is not None:
            print(f"Documento ya existe (id={existing.id}), no se vuelve a ingerir.")
            return

        raw_text = load_libro_cuarto_text()
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
