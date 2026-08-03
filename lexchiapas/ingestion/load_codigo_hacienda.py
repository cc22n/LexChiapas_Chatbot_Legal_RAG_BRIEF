"""Script de ingesta puntual para el Codigo de la Hacienda Publica para el
Estado de Chiapas (area_derecho=fiscal).

Complementa al Codigo Fiscal del Estado de Chiapas ya cargado: el Codigo
Fiscal regula contribuciones/recaudacion, mientras que este Codigo regula
el regimen de ingresos publicos, el gasto publico, el presupuesto de
egresos, la contabilidad gubernamental y la deuda publica del Estado
(Libro Cuarto, "Presupuesto, Gasto, Contabilidad y Deuda Publica").

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerir ni
a generar embeddings de nuevo.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Codigo de la Hacienda Publica para el Estado de Chiapas"

# Dos hosts probados con HEAD/GET request el 2026-07-13:
# - consejeriajuridica.chiapas.gob.mx (host viejo, URL original reportada en
#   el brief): 404, ya no sirve este documento.
# - institutodelaconsejeriajuridica.chiapas.gob.mx (host nuevo): 200 OK.
#
# El host nuevo sirve DOS archivos casi identicos en nombre pero con
# contenido distinto (bug conocido de este sitio, ya visto en otras leyes):
# - "Codigo_dela_haciendapublica_Chiapas.pdf" (sin espacio/guion entre "de"
#   y "la", el nombre EXACTO del brief): 1,158,304 bytes, Last-Modified
#   2024-10-11. Texto interno: "ULTIMA REFORMA ... 15 DE DICIEMBRE DE 2023.
#   DECRETO NUMERO 029." -- VERSION VIEJA.
# - "Codigo_de_la_haciendapublica_Chiapas.pdf" (con guion bajo entre "de" y
#   "la"): 1,490,848 bytes, Last-Modified 2025-02-06. Texto interno:
#   "Ultima reforma publicada ... No. 012, Tomo III, de fecha 22 de enero
#   del 2025. Decreto No. 182." -- VERSION VIGENTE, mas reciente.
#
# Se descargaron y extrajeron AMBOS PDFs y se comparo la fecha de "ultima
# reforma" leida dentro del propio texto (no solo el nombre de archivo ni el
# Last-Modified del servidor, que podrian no reflejar la reforma real). Se
# eligio la version con guion bajo (reforma de enero 2025) por ser la mas
# reciente.
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/Codigo_de_la_haciendapublica_Chiapas.pdf"
)

PROCESSED_TXT = "data/processed/codigo_hacienda_publica.txt"

# Leido del propio PDF (primera pagina): "Ultima reforma publicada en el
# Periodico Oficial No. 012, Tomo III, de fecha 22 de enero del 2025.
# Decreto No. 182." El texto original (nueva creacion) se publico el 18 de
# mayo de 2016 segun la misma pagina (identico dato al que ya tiene el
# Codigo Fiscal, ambos ordenamientos nacieron del mismo decreto de reforma
# hacendaria de 2016).
FECHA_PUBLICACION = date(2016, 5, 18)
FECHA_ULTIMA_REFORMA = date(2025, 1, 22)

# Correcciones puntuales de texto (NO son bugs del chunker compartido, son
# defectos reales del propio PDF fuente en saltos de pagina especificos de
# ESTE documento -- ver docstring de cada una). Se aplican sobre el texto
# extraido ANTES de chunkear. Cada una se verifico contra el PDF pagina por
# pagina con pdfplumber antes de aplicarse.
_TEXT_FIXES = [
    (
        # Bug real: la fraccion VIII del Articulo 2 termina sin punto final
        # en el PDF fuente (no es un artefacto de extraccion: ambas lineas
        # estan en la MISMA pagina de pdfplumber, una debajo de la otra).
        # Sin el punto, la heuristica de "cita a mitad de oracion" de
        # app.rag.chunker._is_midsentence_line trata el encabezado real
        # "Articulo 3.-" como continuacion del Articulo 2 en vez de un
        # limite nuevo, fusionando el Articulo 3 completo dentro del chunk
        # del Articulo 2 (numero de articulo incorrecto para esa cita).
        "VIII. Reglamento: Al Reglamento del Código de la Hacienda "
        "Pública para el Estado de Chiapas\nArtículo 3.-",
        "VIII. Reglamento: Al Reglamento del Código de la Hacienda "
        "Pública para el Estado de Chiapas.\nArtículo 3.-",
    ),
    (
        # Bug real: en la transicion de "Libro Primero" a "Libro Segundo",
        # pdfplumber extrae "Titulo Primero" pegado al FINAL de la linea
        # descriptiva del Libro ("De las Contribuciones, Productos y
        # Aprovechamientos Titulo Primero") en vez de en su propia linea, y
        # lo mismo con "Capitulo Unico" pegado a "Disposiciones Generales".
        # TITULO_RE/CAPITULO_RE en app.rag.chunker exigen que la linea
        # COMPLETA sea el encabezado (o, en el caso flexible, que el
        # ordinal venga AL INICIO de la linea con el texto descriptivo
        # despues, ej. "CAPITULO CUARTO DE LAS PRUEBAS") -- no cubren el
        # caso inverso (texto descriptivo primero, ordinal al final). Sin
        # esta correccion, ni "Titulo Primero" ni "Capitulo Unico" se
        # reconocen como encabezados: quedan pegados como contenido del
        # Articulo 225 anterior, y como esa ultima linea de contenido no
        # cierra en puntuacion, la heuristica de "cita a mitad de oracion"
        # tambien fusiona el Articulo 226 completo dentro del chunk del
        # Articulo 225 (el Articulo 226 desaparecia por completo del
        # chunking).
        "Libro Segundo\nDe las Contribuciones, Productos y Aprovechamientos "
        "Título Primero\nDisposiciones Generales Capítulo "
        "Único\nArtículo 226.-",
        "Libro Segundo\nDe las Contribuciones, Productos y Aprovechamientos"
        "\nTítulo Primero\nDisposiciones Generales\nCapítulo "
        "Único\nArtículo 226.-",
    ),
    (
        # Mismo patron que el fix anterior, en la transicion de "Libro
        # Segundo" a "Libro Tercero": "Titulo Unico" pegado al final de la
        # linea descriptiva del Libro. Aqui el Articulo 270 SI se generaba
        # como chunk (el siguiente encabezado "Capitulo I" viene en su
        # propia linea y si se reconoce), pero con metadata `titulo`
        # incorrecto (arrastraba "Quinto", el ultimo Titulo real del Libro
        # Segundo, en vez de "Unico" del Libro Tercero) -- una cita con
        # Titulo equivocado.
        "Libro Tercero\nDe la Coordinación Hacendaria del Estado de "
        "Chiapas Título Único\nCapítulo I",
        "Libro Tercero\nDe la Coordinación Hacendaria del Estado de "
        "Chiapas\nTítulo Único\nCapítulo I",
    ),
    (
        # Bug real, mas grave: en la transicion al Capitulo VIII del Titulo
        # Segundo del Libro Cuarto, pdfplumber extrae el titulo descriptivo
        # del capitulo PEGADO al encabezado del Articulo 403 que sigue, en
        # una sola linea ("Facultades Exclusivas del Titular del Ejecutivo
        # Articulo 403.- Es"). Como ARTICULO_RE exige que "ARTICULO" este al
        # INICIO de la linea (permitiendo solo espacios antes), esta linea
        # no matchea como encabezado de articulo -- y como el match de
        # "Capitulo VIII" (linea anterior, si reconocido) ya puso
        # current_articulo en None, esta linea (y todo el contenido del
        # Articulo 403 que sigue, hasta el proximo encabezado real) se
        # descartaba en silencio por completo (current_articulo is None):
        # el Articulo 403 entero desaparecia del chunking, no solo se
        # fusionaba con otro articulo.
        "Capítulo VIII\nFacultades Exclusivas del Titular del Ejecutivo "
        "Artículo 403.- Es\nfacultad",
        "Capítulo VIII\nFacultades Exclusivas del Titular del Ejecutivo"
        "\nArtículo 403.- Es\nfacultad",
    ),
]


def _apply_text_fixes(raw_text: str) -> str:
    for old, new in _TEXT_FIXES:
        count = raw_text.count(old)
        if count != 1:
            raise ValueError(
                f"Correccion de texto esperaba 1 ocurrencia, encontro {count}: "
                f"{old[:60]!r}..."
            )
        raw_text = raw_text.replace(old, new)
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

        raw_text = _apply_text_fixes(raw_text)

        legal_chunks = chunk_legal_text(raw_text, document_nombre=DOCUMENT_NOMBRE)
        print(f"chunk_legal_text produjo {len(legal_chunks)} chunks")
        sin_articulo = sum(1 for c in legal_chunks if c.articulo_numero is None)
        print(f"chunks sin articulo_numero: {sin_articulo}")

        numeros = [c.articulo_numero for c in legal_chunks]
        duplicados = {n for n in numeros if numeros.count(n) > 1}
        print(f"numeros de articulo duplicados (chunks separados con mismo numero): {sorted(duplicados)}")

        document = Document(
            nombre=DOCUMENT_NOMBRE,
            tipo="ley",
            fecha_publicacion=FECHA_PUBLICACION,
            fecha_ultima_reforma=FECHA_ULTIMA_REFORMA,
            source_url=SOURCE_URL,
            area_derecho="fiscal",
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
