"""Script de ingesta puntual para el Libro Segundo (De los Bienes) del Codigo
Civil para el Estado de Chiapas (area_derecho=civil).

El Codigo Civil completo (~3000 articulos) se esta cargando en 4 documentos
separados por LIBRO (Primero, Segundo, Tercero, Cuarto), cada uno con su
propio script, para no generar un solo documento gigante. Este script cubre
SOLO el Libro Segundo. El texto ya fue extraido previamente a
data/processed/codigo_civil.txt (901698 caracteres, 17982 lineas); este
script recorta ese archivo a las lineas que corresponden al Libro Segundo
(verificadas manualmente antes de escribir este script) y confirma el corte
por contenido, no solo por numero de linea, antes de seguir.

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.
"""

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = (
    "Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)"
)
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/CODIGO%20CIVIL%20PARA%20EL%20ESTADO%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/codigo_civil.txt"

# Rango de lineas (0-indexed, slice de Python: incluye INICIO, excluye FIN)
# que corresponde al Libro Segundo dentro del texto extraido completo del
# Codigo Civil. Verificado leyendo el archivo directamente antes de escribir
# este script:
#   linea 5256 = "LIBRO SEGUNDO", linea 5257 = "DE LOS BIENES"
#   linea 8137 = "L I B R O   T E R C E R O" (letras espaciadas), linea 8138
#   = "DE LAS SUCESIONES" -- esa linea 8137 y todo lo que sigue es del Libro
#   Tercero, cargado por otro agente en paralelo, y NO debe incluirse aqui.
LIBRO2_START_LINE = 5256
LIBRO2_END_LINE = 8137

# Typo real en el propio PDF fuente (no de extraccion): el encabezado del
# primer capitulo del Titulo Sexto (De las Servidumbres) dice literalmente
# "CAPIULO (SIC) I" en vez de "CAPITULO I" -- el propio documento ya marca el
# typo con "(SIC)". chunker.py exige que la linea completa empiece con la
# palabra "CAPITULO" (ver CAPITULO_RE en app/rag/chunker.py); "CAPIULO" no
# matchea, asi que sin esta correccion la linea cae como contenido normal y
# el metadata `capitulo` de los articulos 1045-1055 (los que estan bajo este
# capitulo real) queda con el valor viejo heredado del ultimo capitulo del
# Titulo Quinto ("V") en vez de "I" -- una mala atribucion de metadata
# exactamente del tipo que la regla de oro del dominio legal prohibe. Es un
# typo puntual de ESTE documento (un solo caracter faltante, ya anotado como
# tal en el propio PDF), no un patron que se repita en otras leyes, asi que
# se corrige aqui con un reemplazo de texto exacto en vez de tocar
# chunker.py. Verificado que la cadena aparece exactamente una vez en la
# porcion del Libro Segundo antes de aplicar el reemplazo.
_CAPIULO_TYPO = "CAPIULO (SIC) I"
_CAPIULO_FIX = "CAPITULO I"


def _load_libro2_text() -> str:
    with open(PROCESSED_TXT, encoding="utf-8") as f:
        lines = f.read().splitlines()

    portion = lines[LIBRO2_START_LINE:LIBRO2_END_LINE]
    if portion[0].strip() != "LIBRO SEGUNDO":
        raise ValueError(
            f"Corte de Libro Segundo invalido: primera linea es {portion[0]!r}, "
            "se esperaba 'LIBRO SEGUNDO'"
        )
    if "L I B R O" in portion[-1].upper() or "TERCERO" in portion[-1].upper():
        raise ValueError(
            f"Corte de Libro Segundo invalido: ultima linea parece ser del "
            f"Libro Tercero: {portion[-1]!r}"
        )

    text = "\n".join(portion)

    occurrences = text.count(_CAPIULO_TYPO)
    if occurrences != 1:
        raise ValueError(
            f"Se esperaba exactamente 1 ocurrencia de {_CAPIULO_TYPO!r}, "
            f"se encontraron {occurrences}. Revisar antes de aplicar el fix."
        )
    text = text.replace(_CAPIULO_TYPO, _CAPIULO_FIX)

    return text


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.nombre == DOCUMENT_NOMBRE).first()
        if existing is not None:
            print(f"Documento ya existe (id={existing.id}), no se vuelve a ingerir.")
            return

        raw_text = _load_libro2_text()
        print(f"Texto del Libro Segundo: {len(raw_text)} caracteres")

        legal_chunks = chunk_legal_text(raw_text, document_nombre=DOCUMENT_NOMBRE)
        print(f"chunk_legal_text produjo {len(legal_chunks)} chunks")
        sin_articulo = sum(1 for c in legal_chunks if c.articulo_numero is None)
        print(f"chunks sin articulo_numero: {sin_articulo}")

        numeros = [c.articulo_numero for c in legal_chunks]
        duplicados = {n for n in numeros if numeros.count(n) > 1}
        print(f"articulo_numero duplicados (mismo numero en >1 chunk): {sorted(duplicados)}")

        document = Document(
            nombre=DOCUMENT_NOMBRE,
            tipo="ley",
            fecha_publicacion=None,
            fecha_ultima_reforma=None,
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
