"""Script de ingesta puntual para la Ley de Asentamientos Humanos,
Ordenamiento Territorial y Desarrollo Urbano del Estado de Chiapas
(area_derecho=desarrollo_urbano).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se introduce el valor NUEVO de area_derecho="desarrollo_urbano" (no existia
en la tabla documents hasta esta ingesta) porque ninguna categoria ya en uso
(administrativo, cultural, penal, transito, salud, familiar, civil,
derechos_humanos, laboral, fiscal, ambiental) encaja semanticamente: esta ley
regula planeacion territorial, uso de suelo, equipamiento urbano y
fraccionamientos, un area del derecho administrativo especializada y
distinta de "administrativo" (que en esta DB se uso para transparencia/
acceso a informacion, no para planeacion urbana). Se decidio reusar este
mismo valor para la Ley de Fraccionamientos y Conjuntos Habitacionales para
el Estado y los Municipios de Chiapas (tambien de este lote de 12), tema
directamente relacionado, en vez de crear una tercera categoria de un solo
documento cada una.

Fechas leidas del propio PDF (encabezado, primeras lineas): "LEY DE NUEVA
CREACION, PUBLICADA MEDIANTE PERIODICO OFICIAL NUMERO 337 SEGUNDA SECCION DE
FECHA 27 DE DICIEMBRE DE 2017" (publicacion original) y "ULTIMA REFORMA
PUBLICADA MEDIANTE PERIODICO OFICIAL NUMERO 096 DE FECHA 18 DE MARZO DEL
2026" (ultima reforma).

Hallazgos reales del chunking (chunk_legal_text sin parche): 216 chunks,
0 sin articulo_numero, rango 1-217, UN gap real (183). Se investigo contra
el texto fuente: el encabezado real del Articulo 183 no tiene el punto
separador entre el numero y el texto ("Articulo 183 La accion urbanistica
por asociacion de interes publico se refiere a las..." en vez de "Articulo
183. La accion..."), asi que ARTICULO_RE no matchea la linea en absoluto (el
patron exige un separador final "." o "-" despues del numero/sufijos) y el
Articulo 183 completo (encabezado incluido) se funde como contenido del
Articulo 182 anterior -- typo puntual de este PDF (el unico caso en todo el
documento de un numero de articulo sin separador; se verifico escaneando
todas las lineas que empiezan con "Articulo NNN" seguido de espacio y letra
en vez de separador). Se corrige agregando el punto que falta.

Despues del parche: 217 chunks, 0 sin articulo_numero, rango 1-217 sin
gaps, sin numeros duplicados.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = (
    "Ley de Asentamientos Humanos, Ordenamiento Territorial y Desarrollo "
    "Urbano del Estado de Chiapas"
)

# URL confirmada con HEAD request (200 OK, application/pdf, 617418 bytes,
# Last-Modified Thu, 26 Mar 2026 20:33:25 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0029.pdf?v=MTA="
PROCESSED_TXT = "data/processed/ley_asentamientos_humanos.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(2017, 12, 27)
FECHA_ULTIMA_REFORMA = date(2026, 3, 18)

# Ver docstring del modulo: typo real del PDF fuente (falta el punto
# separador entre el numero de articulo y el texto).
_GAP_183_TYPO = (
    "Artículo 183 La acción urbanística por asociación de interés público"
)
_GAP_183_FIX = (
    "Artículo 183. La acción urbanística por asociación de interés público"
)


def _normalize_raw_text(raw_text: str) -> str:
    if _GAP_183_TYPO not in raw_text:
        return raw_text
    return raw_text.replace(_GAP_183_TYPO, _GAP_183_FIX)


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
