"""Script de ingesta puntual para el Codigo de Procedimientos Penales para el
Estado de Chiapas, del 09 de Febrero de 2012 (area_derecho=penal).

Sigue el mismo patron sincrono usado para las leyes anteriores: sin Celery,
ejecucion directa contra la DB real via app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a ingerirlo
ni a generar embeddings de nuevo.

Se eligio area_derecho="penal" (no un valor nuevo) porque este codigo es el
complemento procesal del Codigo Penal para el Estado de Chiapas (ya cargado,
documents.id 24): juntos cubren el derecho sustantivo y el proceso penal
completo, igual que el par Codigo de Procedimientos Civiles / Codigo Civil.

Fechas leidas del propio PDF (encabezado, primeras lineas): "Ley publicada
mediante decreto 147, en el Periodico Oficial del Estado numero 353-3a.
Seccion de fecha 09 de Febrero de 2012" (publicacion original) y "ULTIMA
REFORMA PUBLICADA EN EL PERIODICO OFICIAL DEL ESTADO NUMERO 156-3a. SECCION
DE FECHA 24 DE DICIEMBRE DE 2014" (ultima reforma).

Hallazgos reales del chunking (chunk_legal_text sin parche): 567 chunks,
0 sin articulo_numero, rango 1-562, DOS gaps reales (423, 553) y UN numero
de articulo duplicado real (478). Se investigaron los tres contra el texto
fuente antes de decidir un parche puntual (no se asumio bug generico del
chunker; el chunker YA fue corregido de forma general en esta misma tanda de
ingesta para el bug estructural de "TITULO/CAPITULO con punto final" que si
afecto al Codigo de Procedimientos Civiles -- ver comentario junto a
_HEADER_LABEL_RE en app/rag/chunker.py -- pero este documento en particular
NO usa esa convencion: sus encabezados de Titulo/Capitulo/Seccion son
simples, sin punto final ("Titulo Primero", "Capitulo I", "Seccion 1"), y la
jerarquia se detecto correctamente sin necesidad de ningun parche adicional
para eso):

1. Gaps de los Articulos 423 y 553: mismo patron ya visto en
   load_codigo_procedimientos_civiles.py (Articulo 846) y en
   load_ley_discapacidad.py (Articulo 47) -- la ultima linea de contenido
   del articulo anterior no cierra con punto final justo antes del
   encabezado real del siguiente articulo ("...para ello o para
   certificarlos" antes de "Articulo 423.", y "...terminos de este mismo
   Codigo" antes de "Articulo 553."), asi que _is_midsentence_line trata el
   encabezado real como cita a mitad de oracion y lo funde como contenido
   del articulo previo, hasta que el articulo entero desaparece del
   chunking. Se corrige agregando el punto final que falta.
2. Duplicado del "478": distinto de los dos casos anteriores. Este
   documento tiene una lista enumerada de materias de la Fiscalia
   Especializada en Combate a la Corrupcion (items "22)", "33)", "34)",
   etc.), y el item 33 ("33) Operaciones con recursos de procedencia
   ilicita, previsto y sancionado por el") se corta a mitad de oracion justo
   al inicio de una nueva linea de PDF ("articulo 478."), exactamente el
   patron de cita a mitad de oracion que ARTICULO_RE ya sabe reconocer via
   _is_midsentence_line -- EXCEPTO que la excepcion de _ENUM_ITEM_RE (que
   trata un item de lista enumerada como "ya cerrado" aunque le falte
   puntuacion, pensada para el caso real del Codigo Penal donde el item de
   lista ES la ultima pieza real de contenido de un articulo) se dispara
   aqui de forma incorrecta: la ultima linea de contenido antes de la
   cita cortada es ELLA MISMA un item de lista enumerada sin terminar
   ("33) ... por el"), no el cierre real del articulo activo. El resultado
   sin parche: "articulo 478." se reconoce como encabezado nuevo (real, pero
   en el lugar equivocado -- esto NO es realmente el Articulo 478, es solo
   una referencia cruzada dentro del contenido del articulo activo en ese
   momento), colisionando con el Articulo 478 real que aparece mas adelante
   en el documento ("Articulo 478. Casos de ausencia del funcionario
   imputado") bajo el mismo numero. Se verifico que es un caso AISLADO (una
   sola coincidencia real de este patron especifico en todo el documento,
   confirmado escaneando cada linea que matchea ARTICULO_RE contra su linea
   anterior). Se corrige uniendo esa cita cortada a la linea anterior (quita
   el salto de linea que hace que "articulo 478." empiece su propia linea),
   sin alterar el texto legal en si.

Despues de los tres parches: 568 chunks, 0 sin articulo_numero, rango 1-562
sin gaps, sin numeros duplicados.
"""

from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import chunk_legal_text
from app.rag.embeddings import embed_and_store_chunks

DOCUMENT_NOMBRE = "Codigo de Procedimientos Penales para el Estado de Chiapas"

# URL confirmada con HEAD request (200 OK, application/pdf, 994336 bytes,
# Last-Modified Fri, 15 Mar 2019 15:01:36 GMT) el 2026-07-30. Tomada
# directamente de ingestion/scrapers/congreso_scraper.py::list_available_laws()
# (fuente ya verificada, 146 filas reales del sitio de Congreso).
SOURCE_URL = (
    "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/"
    "codigo%20de%20procedimientos%20penales%20para%20el%20estado%20de%20"
    "chiapas,%20del%2009%20de%20febrero%20de%202012..pdf?v=NA=="
)
PROCESSED_TXT = "data/processed/codigo_procedimientos_penales.txt"

# Leido del propio PDF (encabezado, primeras lineas). Ver docstring del
# modulo.
FECHA_PUBLICACION = date(2012, 2, 9)
FECHA_ULTIMA_REFORMA = date(2014, 12, 24)

# Ver docstring del modulo: tres typos puntuales de este PDF fuente.
_GAP_423_TYPO = (
    "expedidos por quien tenga competencia para ello o para certificarlos\n"
    "Artículo 423."
)
_GAP_423_FIX = (
    "expedidos por quien tenga competencia para ello o para certificarlos.\n"
    "Artículo 423."
)
_GAP_553_TYPO = "términos de este mismo Código\nArtículo 553."
_GAP_553_FIX = "términos de este mismo Código.\nArtículo 553."
_DUP_478_TYPO = "previsto y sancionado por el\nartículo 478.\n34)"
_DUP_478_FIX = "previsto y sancionado por el artículo 478.\n34)"


def _normalize_raw_text(raw_text: str) -> str:
    if _GAP_423_TYPO in raw_text:
        raw_text = raw_text.replace(_GAP_423_TYPO, _GAP_423_FIX)
    if _GAP_553_TYPO in raw_text:
        raw_text = raw_text.replace(_GAP_553_TYPO, _GAP_553_FIX)
    if _DUP_478_TYPO in raw_text:
        raw_text = raw_text.replace(_DUP_478_TYPO, _DUP_478_FIX)
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
