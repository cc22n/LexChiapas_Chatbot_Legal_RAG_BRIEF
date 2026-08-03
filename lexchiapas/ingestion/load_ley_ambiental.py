"""Script de ingesta puntual para la Ley Ambiental para el Estado de Chiapas
(area_derecho=ambiental).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.

Nota sobre chunker.py: NO se modifico. Se leyo app/rag/chunker.py y
tests/test_chunker.py antes de asumir cualquier bug nuevo. El chunking de
este documento salio limpio en el primer intento: 237 chunks, uno por cada
Articulo 1 a 237, sin huecos ni duplicados, y sin ningun chunk con
articulo_numero nulo. No se encontro ningun typo puntual del PDF fuente que
requiriera un parche de texto como el de otras leyes (ver
load_ley_transparencia.py para un ejemplo de ese tipo de parche).

Nota sobre posible duplicado con otra ley: se comparo el nombre y el
preambulo (Decreto Numero 189, publicada el 18 de marzo de 2009 en la
Tercera Seccion del Periodico Oficial) contra las 12 leyes ya activas en la
DB (consultadas via Document.nombre/source_url) y no hay ninguna coincidencia
de nombre ni de numero de decreto -- no parece ser el mismo caso que
Codigo Fiscal / Codigo de la Hacienda Publica.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley Ambiental para el Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 635358 bytes,
# Last-Modified Fri, 11 Oct 2024 14:21:57 GMT) el 2026-07-13. El host viejo
# (consejeriajuridica.chiapas.gob.mx) dio 404 con el mismo nombre de
# archivo; el host nuevo (institutodelaconsejeriajuridica.chiapas.gob.mx)
# si lo sirve, siguiendo el mismo patron ya visto con otras leyes recientes.
# Se reviso el indice de list_available_laws() (ingestion/scrapers/
# consejeria_scraper.py) y solo aparece UNA entrada para esta ley (mismo
# nombre de archivo); no se encontro una segunda URL candidata con nombre
# distinto que hiciera falta comparar por fecha de ultima reforma.
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/LEY%20AMBIENTAL%20PARA%20EL%20ESTADO%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/ley_ambiental.txt"

# Leido del propio PDF (primera pagina): "Ley publicada en la Tercera
# Seccion del Periodico Oficial del Estado de Chiapas, el miercoles 18 de
# marzo de 2009" (Decreto Numero 189); "ULTIMA REFORMA PUBLICADA EN EL
# PERIODICO OFICIAL: 4 DE ABRIL DE 2012."
FECHA_PUBLICACION = date(2009, 3, 18)
FECHA_ULTIMA_REFORMA = date(2012, 4, 4)


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

        numericos = sorted({int(n) for n in numeros if n and n.isdigit()})
        if numericos:
            gaps = [n for n in range(numericos[0], numericos[-1] + 1) if n not in numericos]
            print(f"rango numerico {numericos[0]}-{numericos[-1]}, gaps: {gaps if gaps else 'ninguno'}")

        document = Document(
            nombre=DOCUMENT_NOMBRE,
            tipo="ley",
            fecha_publicacion=FECHA_PUBLICACION,
            fecha_ultima_reforma=FECHA_ULTIMA_REFORMA,
            source_url=SOURCE_URL,
            area_derecho="ambiental",
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
