"""Script de ingesta puntual para el Codigo Penal para el Estado de Chiapas
(area_derecho=penal).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.

Motivacion real: el corpus ya tenia la Ley de Amnistia (area penal, un
indulto puntual de 1994) pero ningun codigo penal sustantivo. Una pregunta
de prueba sobre la pena del delito de robo no tenia fundamento real en el
corpus (ver tests/test_rag_regression.py, test_no_encontrado_codigo_penal,
actualizado en esta misma sesion para reflejar que ahora si esta cargado).
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Codigo Penal para el Estado de Chiapas"

# URL confirmada por ingestion/scrapers/congreso_scraper.py (list_available_laws)
# contra el listado real de "legislacion vigente" del Congreso del Estado:
# nombre exacto en la fuente "CODIGO PENAL PARA EL ESTADO DE CHIAPAS". Descargada
# el 2026-07-20 (1318346 bytes).
SOURCE_URL = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0012.pdf?v=NDM="

PROCESSED_TXT = "data/processed/codigo_penal.txt"

# Leido del propio PDF (primera pagina): "TEXTO NUEVA CREACION. PUBLICADA EN
# EL PERIODICO No 14 DE MARZO DE 2007." (Decreto Numero 139); "ULTIMA REFORMA
# PUBLICADA MEDIANTE PERIODICO OFICIAL NUMERO 103 DE FECHA 29 DE ABRIL DEL
# 2026. DECRETO NUMERO 229." (Nota: el PDF tambien reporta, por separado, una
# invalidez parcial del Articulo 326 Bis resuelta por la SCJN el 23 de
# febrero de 2026 con efectos retroactivos al 19 de junio de 2025 -- eso es
# una resolucion judicial, no una reforma legislativa nueva, asi que no se
# usa como fecha_ultima_reforma).
FECHA_PUBLICACION = date(2007, 3, 14)
FECHA_ULTIMA_REFORMA = date(2026, 4, 29)


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

        numericos = sorted(
            {
                int(n.split(" ")[0].split("-")[0])
                for n in numeros
                if n and n.split(" ")[0].split("-")[0].isdigit()
            }
        )
        if numericos:
            gaps = [n for n in range(numericos[0], numericos[-1] + 1) if n not in numericos]
            print(f"rango numerico {numericos[0]}-{numericos[-1]}, gaps: {gaps if gaps else 'ninguno'}")

        document = Document(
            nombre=DOCUMENT_NOMBRE,
            tipo="ley",
            fecha_publicacion=FECHA_PUBLICACION,
            fecha_ultima_reforma=FECHA_ULTIMA_REFORMA,
            source_url=SOURCE_URL,
            area_derecho="penal",
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
