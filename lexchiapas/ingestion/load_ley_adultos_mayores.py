"""Script de ingesta puntual para la Ley de Asistencia e Integracion de las
Personas Adultas Mayores del Estado de Chiapas (area_derecho=familiar).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="familiar" (no un valor nuevo) por el mismo motivo
documentado en load_ley_discapacidad.py: es la categoria ya usada en la DB
para leyes de grupos vulnerables/familia (Codigo de Atencion a la Familia y
Grupos Vulnerables, Ley de Adopcion, Ley de Derechos de NNA). No existe una
categoria "asistencia_social" ya en uso; se prefirio reusar "familiar" en
vez de introducir una categoria nueva de un solo documento.

Motivo de esta ingesta: esta ley aparece citada 89 veces como destino de
relaciones cross-ley (marcadores REFORMADO/DEROGADO/ADICIONADO dentro de
otras leyes ya ingeridas, incluido el Articulo Tercero Transitorio de la
Ley para la Inclusion de las Personas con Discapacidad, que derogo el
Libro Cuarto del Codigo de Atencion a la Familia) que quedaron con
to_document_id=NULL en legal_relations porque el documento nunca existia en
la DB. Ver ingestion/extract_legal_relations.py: se debe re-correr ese
script despues de esta ingesta para que esas 89 relaciones se re-resuelvan
contra el Document recien creado.

Nota sobre chunker.py: NO se modifico. Se leyo app/rag/chunker.py y
tests/test_chunker.py antes de asumir cualquier bug nuevo. El chunking de
este documento salio limpio en el primer intento: 93 chunks, uno por cada
Articulo 1 a 93, sin huecos ni duplicados, y sin ningun chunk con
articulo_numero nulo -- a pesar de que el PDF fuente tiene 35 pies de
pagina intercalados (marca de tiempo + numero de pagina, ej. "17/10/2022
02:23 p.m. 13"), el mismo patron de ruido ya cubierto por FOOTER_RE en
chunker.py (documentado ahi mismo con el mismo formato exacto, visto
tambien en 8 de las 14 leyes ya ingeridas: Codigo de Atencion a la Familia,
Codigo Civil, Ley de Adopcion, Ley de Bibliotecas, Ley de Amnistia, Ley del
Notariado, Ley del Servicio Civil, Ley de Tortura). Se escaneo ademas todo
el texto buscando lineas de contenido antes de cada encabezado real de
Articulo que no cerraran en puntuacion (mismo chequeo que uso
load_ley_discapacidad.py para encontrar su gap real): las unicas
coincidencias son titulos de Capitulo/Seccion en su propia linea o pies de
pagina ya filtrados por FOOTER_RE, ninguna es contenido de articulo activo,
asi que no hay ningun caso oculto de fusion de articulos en este documento.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de Asistencia e Integracion de las Personas Adultas Mayores del Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 414298 bytes,
# Last-Modified Fri, 11 Oct 2024 14:21:58 GMT) el 2026-07-24. Encontrada en
# el indice de list_available_laws() (ingestion/scrapers/
# consejeria_scraper.py): unica entrada con nombre "LEY DE ASISTENCIA E
# INTEGRACION DE LAS PERSONAS ADULTAS MAYORES DEL ESTADO DE CHIAPAS." en el
# listado de la Consejeria Juridica. El host viejo del href original
# (consejeriajuridica.chiapas.gob.mx) dio 404 con el mismo nombre de
# archivo; el host nuevo (institutodelaconsejeriajuridica.chiapas.gob.mx) si
# lo sirve, siguiendo el mismo patron ya visto con otras leyes recientes.
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/LEY%20DE%20ASISTENCIA%20E%20INTEGRACI%C3%93N%20DE%20LAS%20"
    "PERSONAS%20ADULTAS%20MAYORES%20DEL%20ESTADO%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/ley_adultos_mayores.txt"

# Leido del propio PDF (encabezado de la primera pagina): "Ultima reforma
# publicada en el Periodico Oficial No. 217, Decreto No. 143, Tomo III de
# fecha jueves 31 de diciembre de 2015". El texto extraido no incluye el
# numero/fecha exacta del Periodico Oficial de la publicacion original (solo
# la ultima reforma referenciada en el encabezado); no se asume una fecha de
# creacion distinta a la unica que el propio documento declara.
FECHA_PUBLICACION = None
FECHA_ULTIMA_REFORMA = date(2015, 12, 31)


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
            area_derecho="familiar",
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
