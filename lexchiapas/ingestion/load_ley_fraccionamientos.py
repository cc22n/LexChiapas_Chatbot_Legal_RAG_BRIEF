"""Script de ingesta puntual para la Ley de Fraccionamientos y Conjuntos
Habitacionales para el Estado y los Municipios de Chiapas
(area_derecho=desarrollo_urbano).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="desarrollo_urbano" (mismo valor nuevo introducido en
esta misma tanda por load_ley_asentamientos_humanos.py, ver docstring de ese
modulo) porque esta ley regula directamente los fraccionamientos y conjuntos
habitacionales -- el mismo tema (vivienda/urbanismo) que la Ley de
Asentamientos Humanos, Ordenamiento Territorial y Desarrollo Urbano, que de
hecho cita expresamente a esta ley ("Autorizar, con base en la Ley de
Fraccionamientos, la fusion, subdivision, fraccionamiento...", Articulo 14).
Se comparo contenido contra esa ley y contra otros documentos que mencionan
"fraccionamiento" (Ley Ambiental id 19, Codigo Penal id 24, Ley de
Discapacidad id 26) y se confirmo que ninguno duplica el contenido
sustantivo de esta ley: solo la mencionan de paso o hacen referencia
cruzada a ella.

Fechas leidas del propio PDF (encabezado, primeras lineas): "Ley publicada
mediante decreto 303, en el Periodico Oficial del Estado numero 193 de
fecha 21 de octubre de 2009" (publicacion original) y "ULTIMA REFORMA
PUBLICADA MEDIANTE PERIODICO OFICIAL NUMERO 020 DE FECHA 13 DE FEBRERO DE
2025" (ultima reforma).

Hallazgos reales del chunking: 142 chunks, 0 sin articulo_numero, rango
1-141, SIN ningun gap ni numero de articulo duplicado en cuanto a numeros de
articulo. Jerarquia Titulo > Capitulo > Seccion detectada correctamente.

Se encontro y corrigio un bug REAL y GENERAL en el chunker compartido
(app/rag/chunker.py, TRANSITORIO_RE) al ingerir este documento: el
encabezado real de la seccion de Transitorios en este PDF es
"TRANSITORIOS." con PUNTO FINAL pegado (misma convencion tipografica ya
corregida para TITULO/CAPITULO/SECCION por el Codigo de Procedimientos
Civiles, cargado antes en esta misma tanda). TRANSITORIO_RE no aceptaba ese
punto, asi que la seccion de transitorios nunca se reconocia como limite, y
TODO su contenido (incluyendo las firmas y fecha del decreto al final del
archivo completo) se fusionaba silenciosamente como contenido del ultimo
articulo real (Articulo 141) -- un chunk final contaminado con texto no
normativo. Se corrigio TRANSITORIO_RE para aceptar un punto final opcional
(mismo tipo de fix que _HEADER_LABEL_RE). Se verifico que NINGUNO de los
otros 5 documentos ya cargados en esta misma tanda (Codigo de Procedimientos
Civiles, Codigo de Procedimientos Penales, Ley de Aguas, Ley de
Asentamientos Humanos, Ley de Derechos y Culturas Indigenas, Ley Forestal)
usa esta convencion con punto en su primer encabezado real de Transitorios
(se escaneo el texto fuente de cada uno), asi que ninguno de ellos necesita
ser re-ingerido por este bug -- solo esta ley se vio afectada, y este script
ya se ejecuto DESPUES del fix (no hizo falta un segundo re-ingreso para
este documento en particular; el primer intento de carga si tuvo que
descartarse y reingerir despues de aplicar el fix, ver commit/historial de
este archivo).

Despues del fix compartido: el chunk del Articulo 141 termina limpio en
"...mediante el recurso que establece la Ley de Procedimientos
Administrativos para el Estado de Chiapas." (424 caracteres), sin ningun
texto de transitorios ni firmas pegado.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = (
    "Ley de Fraccionamientos y Conjuntos Habitacionales para el Estado y "
    "los Municipios de Chiapas"
)

# URL confirmada con HEAD request (200 OK, application/pdf, 293284 bytes,
# Last-Modified Wed, 29 Oct 2025 16:19:06 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0041.pdf?v=NQ=="
PROCESSED_TXT = "data/processed/ley_fraccionamientos.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(2009, 10, 21)
FECHA_ULTIMA_REFORMA = date(2025, 2, 13)


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
            area_derecho="desarrollo_urbano",
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
