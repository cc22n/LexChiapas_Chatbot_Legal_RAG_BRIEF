"""Script de ingesta puntual para la Ley para la Inclusion de las Personas
con Discapacidad del Estado de Chiapas (area_derecho=familiar).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="familiar" (no un valor nuevo) porque es el mismo
valor ya usado para el Codigo de Atencion a la Familia y Grupos Vulnerables
(que hasta la reforma de 2015 incluia, en su Libro Cuarto derogado, las
disposiciones sobre Personas con Discapacidad que esta Ley reemplazo -- ver
Articulo Segundo Transitorio de esta misma Ley) y para la Ley de Adopcion y
la Ley de Derechos de NNA -- todas leyes de grupos vulnerables/familia bajo
la misma categoria en la DB actual. No existe una categoria
"asistencia_social" ya en uso; se prefirio reusar "familiar" en vez de
introducir una categoria nueva de un solo documento.

Motivo de esta ingesta: esta ley aparece citada 70 veces como destino de
relaciones cross-ley (marcadores REFORMADO/DEROGADO/ADICIONADO dentro de
otras leyes ya ingeridas) que quedaron con to_document_id=NULL en
legal_relations porque el documento nunca existia en la DB. Ver
ingestion/extract_legal_relations.py: se debe re-correr ese script despues
de esta ingesta para que esas 70 relaciones se re-resuelvan contra el
Document recien creado.

Nota sobre chunker.py: NO se modifico. Se leyo app/rag/chunker.py y
tests/test_chunker.py antes de asumir cualquier bug nuevo. El chunking de
este documento salio con 56 chunks, articulos 1 a 57 (56 numeros distintos,
sin duplicados), pero con UN gap real detectado al comparar el rango
numerico esperado: faltaba el Articulo 47 hasta aplicar el parche de abajo.

Se investigo ese gap contra el texto fuente (no se asumio que fuera un bug
del chunker): es un typo puntual de ESTE PDF, no un patron estructural
generico. La ultima linea de contenido del Articulo 46 ("...el Secretario
Tecnico previsto en la fraccion III, tendra derecho a voz y no a voto") no
cierra con puntuacion (falta el punto final) justo antes del encabezado
real del Articulo 47. La misma heuristica de "cita a mitad de oracion" ya
documentada en chunker.py (ver ARTICULO_RE y _is_midsentence_line, y el
mismo tipo de caso corregido en load_ley_transparencia.py para el Articulo
72 de esa ley) exige que la ultima linea cierre en '.', ':', ';' o ')' para
reconocer el siguiente encabezado como limite nuevo de articulo; sin punto
final ahi, el Articulo 47 completo (incluido su propio encabezado) se
fusionaba silenciosamente como contenido del Articulo 46, y el Articulo 47
desaparecia del chunking.

Se verifico que es un caso AISLADO en este documento: se escaneo todo el
texto buscando, para cada encabezado real de Articulo, si la linea de
contenido no vacia inmediatamente anterior no cerraba en puntuacion. De 10
coincidencias, 9 son titulos de Capitulo/Seccion en su propia linea (que no
disparan el problema porque flush() ya resetea current_articulo antes de
llegar al Articulo) y solo esta (antes del Articulo 47) es contenido normal
de un articulo activo. Por ser un typo puntual de este PDF y no un patron
estructural, se corrige aqui con un reemplazo de texto exacto, no en la
heuristica compartida de chunker.py.

Despues del parche: 57 chunks, articulos 1 a 57, sin huecos, sin
duplicados, sin ningun chunk con articulo_numero nulo.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley para la Inclusion de las Personas con Discapacidad del Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 132250 bytes,
# Last-Modified Fri, 11 Oct 2024 14:22:09 GMT) el 2026-07-24. Encontrada en
# el indice de list_available_laws() (ingestion/scrapers/
# consejeria_scraper.py): unica entrada con nombre "LEY PARA LA INCLUSION DE
# LAS PERSONAS CON DISCAPACIDAD DEL ESTADO DE CHIAPAS." en el listado de la
# Consejeria Juridica. El host viejo del href original
# (consejeriajuridica.chiapas.gob.mx) dio 404 con el mismo nombre de
# archivo; el host nuevo (institutodelaconsejeriajuridica.chiapas.gob.mx) si
# lo sirve, siguiendo el mismo patron ya visto con otras leyes recientes.
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/LEY%20PARA%20LA%20INCLUSI%C3%93N%20DE%20LAS%20PERSONAS%20CON%20"
    "DISCAPACIDAD%20DEL%20ESTADO%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/ley_discapacidad.txt"

# Leido del propio PDF: creacion original mediante Decreto publicado en el
# Periodico Oficial el 21 de septiembre de 2015 (fecha del Decreto y de su
# promulgacion; el texto extraido no incluye el numero/fecha exacta del
# Periodico Oficial de esta publicacion original, solo la fecha del acta de
# sesion y promulgacion). Ultima reforma: "Publicado en el Periodico Oficial
# Numero 287 de fecha miercoles 14 de junio de 2023, Tomo III, Decreto
# Numero 197" (encabezado de la primera pagina del PDF, confirmado tambien
# por el bloque de Transitorios final del propio documento).
FECHA_PUBLICACION = date(2015, 9, 21)
FECHA_ULTIMA_REFORMA = date(2023, 6, 14)

# Ver docstring del modulo: typo real del PDF fuente (falta el punto final
# de la ultima linea de contenido del Articulo 46), corregido aqui de forma
# puntual antes de pasar el texto al chunker compartido.
_ARTICULO_46_TYPO = "derecho a voz y no a voto\nArtículo 47."
_ARTICULO_46_FIX = "derecho a voz y no a voto.\nArtículo 47."


def _normalize_raw_text(raw_text: str) -> str:
    if _ARTICULO_46_TYPO not in raw_text:
        # El typo ya no esta presente (PDF actualizado) o el texto cambio;
        # no aplicar el parche a ciegas.
        return raw_text
    return raw_text.replace(_ARTICULO_46_TYPO, _ARTICULO_46_FIX)


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
