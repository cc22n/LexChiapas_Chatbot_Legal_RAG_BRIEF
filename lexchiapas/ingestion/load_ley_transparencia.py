"""Script de ingesta puntual para la Ley de Transparencia y Acceso a la
Informacion Publica del Estado de Chiapas (area_derecho=administrativo).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.

Nota sobre chunker.py: NO se modifico. Se leyo app/rag/chunker.py y
tests/test_chunker.py antes de asumir cualquier bug. Un bug real de
ordinales femeninos para SECCION (necesario para esta ley: "Seccion
Segunda" entre el Articulo 8 y el Articulo 9) ya estaba siendo corregido en
paralelo por otro agente (cargando la Ley del Servicio Civil) mientras se
preparaba este script -- se detecto un choque de escritura real al intentar
editar chunker.py con ese fix ya aplicado por el otro agente (el archivo
habia cambiado desde la ultima lectura). Se reintento tras una espera breve
y se confirmo que el fix ya estaba presente (con su propio test de
regresion en tests/test_chunker.py: test_real_document_feminine_seccion_
ordinal_is_detected), asi que no hizo falta ninguna edicion propia ahi.

Se encontro un segundo problema, este si unico de esta ley y NO generico
(se corrige aqui, no en chunker.py): el Articulo 72 (fraccion VI) termina
en el PDF fuente sin puntuacion de cierre ("...su seguimiento" sin punto
final) justo antes del encabezado real del Articulo 73. La heuristica
compartida de "cita a mitad de oracion" de chunker.py (que protege contra
fusionar citas reales como "ARTICULO 4o. DE ESTE ORDENAMIENTO." dentro del
articulo que las menciona, ver Ley de Tortura en tests/test_chunker.py)
exige que la ultima linea de contenido cierre en '.', ':', ';' o ')' para
reconocer un encabezado siguiente como limite nuevo; sin punto final ahi,
el Articulo 73 completo (incluido su propio encabezado) se fusionaba
silenciosamente como contenido del Articulo 72, y el Articulo 73
desaparecia del chunking (0 chunks con numero '73', gap real detectado
comparando el rango numerico 1-190 esperado contra los numeros de articulo
efectivamente emitidos). Se verifico que es un caso AISLADO en este
documento (se escaneo todo el texto buscando lineas antes de cada
encabezado real de Articulo que no cerraran en puntuacion: de 33
coincidencias, 32 son titulos descriptivos de Capitulo/Seccion en su propia
linea -- que no disparan el problema porque flush() ya resetea
current_articulo antes de llegar al Articulo -- y solo esta es contenido
normal de articulo activo). Por ser un typo puntual de ESTE PDF y no un
patron estructural que afecte a otras leyes, se corrige aqui con un
reemplazo de texto exacto (no en la heuristica compartida de chunker.py,
que ya esta validada contra 9 leyes reales y no debe tocarse por un unico
caracter faltante en un documento distinto).
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Ley de Transparencia y Acceso a la Informacion Publica del Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 897746 bytes,
# Last-Modified 2026-07-03) el 2026-07-13. El host viejo
# (consejeriajuridica.chiapas.gob.mx) dio 404 con el mismo nombre de
# archivo; el host nuevo (institutodelaconsejeriajuridica.chiapas.gob.mx)
# si lo sirve, siguiendo el mismo patron ya visto con otras leyes recientes.
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/LeyTransparencia_Chiapas.pdf"
)
PROCESSED_TXT = "data/processed/ley_transparencia.txt"

# Leido del propio PDF (primera pagina): texto de nueva creacion publicado
# en el Periodico Oficial numero 045, Tomo III, de fecha 18 de junio de
# 2025 (Decreto numero 276); fe de erratas publicada en el Periodico
# Oficial numero 046, de fecha 25 de junio de 2025; ultima reforma
# publicada en el Periodico Oficial numero 113, Tomo III, de fecha 17 de
# junio de 2026 (Decreto numero 258).
FECHA_PUBLICACION = date(2025, 6, 18)
FECHA_ULTIMA_REFORMA = date(2026, 6, 17)

# Ver docstring del modulo: typo real del PDF fuente (falta el punto final
# de la fraccion VI del Articulo 72), corregido aqui de forma puntual antes
# de pasar el texto al chunker compartido.
_ARTICULO_72_TYPO = "el estado en que se encuentran y su seguimiento\nArtículo 73.-"
_ARTICULO_72_FIX = "el estado en que se encuentran y su seguimiento.\nArtículo 73.-"


def _normalize_raw_text(raw_text: str) -> str:
    if _ARTICULO_72_TYPO not in raw_text:
        # El typo ya no esta presente (PDF actualizado) o el texto cambio;
        # no aplicar el parche a ciegas.
        return raw_text
    return raw_text.replace(_ARTICULO_72_TYPO, _ARTICULO_72_FIX)


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
            area_derecho="administrativo",
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
