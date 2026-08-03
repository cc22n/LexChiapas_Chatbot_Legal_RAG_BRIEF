"""Script de ingesta puntual para la Ley de Salud del Estado de Chiapas
(area_derecho=salud).

Sigue el mismo patron sincrono usado para las leyes anteriores (Amnistia,
Bibliotecas, Tortura, Adopcion, Codigo de Atencion a la Familia, Ley de los
Derechos de NNA): sin Celery, ejecucion directa contra la DB real via
app.database.SessionLocal().

Idempotente: si el documento ya existe (por nombre), no vuelve a insertarlo
ni a generar embeddings de nuevo.

Nota sobre chunking (NO se modifico app/rag/chunker.py):
app/rag/chunker.py estaba siendo editado en paralelo por otro agente (cargando
el Codigo Fiscal) mientras se preparaba este script -- se detecto un choque
de escritura real al intentar leer/editar ese archivo compartido. Para no
arriesgar el trabajo concurrente de ese otro agente, este script NO toca
chunker.py. En su lugar, reimplementa localmente (solo para esta ley, sin
tocar el modulo compartido) la deteccion de encabezados de Titulo/Capitulo/
Seccion con una validacion mas estricta, reutilizando de app.rag.chunker todo
lo demas (ARTICULO_RE, TRANSITORIO_RE, FOOTER_RE, _strip_accents, LegalChunk).

Bugs reales encontrados en el texto de esta ley que motivan la
reimplementacion local:

1. Colapso de metadata de Titulo/Capitulo/Seccion: TITULO_RE/CAPITULO_RE/
   SECCION_RE originales (`[A-Z0-9]+` de una sola palabra, sin anclar a fin
   de linea) solo capturan la primera palabra del ordinal. La Ley de Salud
   tiene titulos con ordinal compuesto ("TITULO DECIMO", "TITULO DECIMO
   PRIMERO", ..., "TITULO DECIMO SEXTO", 7 titulos distintos), asi que el
   regex original deja 180 de 289 chunks (62%) con el mismo valor de
   metadata `titulo="DECIMO"` en vez de su titulo real.
2. Falsos positivos a mitad de oracion en Titulo/Capitulo/Seccion: frases
   reales como "...SERA SANCIONADA EN LOS TERMINOS PREVISTOS POR EL TITULO
   DECIMO QUINTO DE ESTA LEY." (Articulo 254) o "...LOS ESTABLECIMIENTOS A
   QUE SE REFIERE ESTE CAPITULO PUEDAN INICIAR SUS OPERACIONES..." (Articulo
   236) matcheaban como si fueran un encabezado nuevo, cortando el articulo
   activo a mitad de frase y perdiendo su contenido final.
3. Sufijos ordinales latinos separados por espacio en ARTICULO_RE: esta ley
   usa profusamente numeros de articulo "adicionados" con sufijo latino
   SEPARADO POR ESPACIO del numero base ("ARTICULO 117 BIS.-", "ARTICULO 125
   QUATTOUR.-", hasta "ARTICULO 117 QUADRAGINTA.-"). El ARTICULO_RE
   compartido (aun con el fix de sufijo "-A"/"-B" pegado con guion) solo
   soporta sufijo de letra PEGADO al numero o con guion, no un sufijo de
   PALABRA separado por espacio. Se encontraron 94 encabezados reales de
   articulo con este patron que ARTICULO_RE no matchea en absoluto -- cada
   uno se fusionaba silenciosamente como contenido del articulo anterior,
   perdiendo su propio numero de articulo citable (94 articulos reales
   "desaparecidos" del chunking, el tipo de bug que la regla de oro del
   dominio legal prohibe).
4. Ruido de salto de pagina que rompe la heuristica de "cita a mitad de
   oracion": pdfplumber extrae, al inicio de CADA una de las 136 paginas de
   este PDF, un numero de pagina suelto ("21") seguido del titulo de la ley
   repetido ("LEY DE SALUD DEL ESTADO DE CHIAPAS") -- un patron de pie/
   encabezado de pagina DISTINTO del que ya cubre FOOTER_RE (que solo
   reconoce el formato "fecha hora a.m./p.m. numero" visto en la Ley de
   Amnistia). Como estas dos lineas no matchean FOOTER_RE ni ningun otro
   limite, quedaban pegadas como contenido normal del articulo activo, y la
   ultima de ellas (el titulo repetido, que NO termina en '.', ':', ';' ni
   ')') se convertia en la `last_nonblank_line` que usa el chequeo de "cita a
   mitad de oracion" de ARTICULO_RE. Eso hacia que CUALQUIER encabezado de
   articulo real que cayera justo despues de un salto de pagina se tratara
   como referencia a mitad de oracion en vez de limite nuevo, fusionando el
   articulo completo siguiente dentro del anterior. Caso real encontrado:
   el ARTICULO 41 completo (sobre obligaciones de los usuarios) desaparecia
   fusionado dentro del chunk del ARTICULO 40 (sobre derechos de los
   usuarios/pacientes) por esta causa. Se filtran ambas lineas de ruido de
   pagina (numero de pagina suelto y titulo de ley repetido) igual que
   FOOTER_RE: se descartan por completo, no se agregan a ningun chunk.

La correccion local para (1)/(2) exige que, despues de la palabra clave
(TITULO/CAPITULO/SECCION), el resto de la linea sea SOLO un ordinal
reconocido (romano, "UNICO", ordinal compuesto tipo "DECIMO SEGUNDO"/"NOVENO
BIS", o numero), opcionalmente con una anotacion entre parentesis como "(A)"
o "(SIC)", y nada mas -- si sobra texto en la linea, se trata como contenido
normal del articulo activo en vez de como limite estructural nuevo.

La correccion local para (3) agrega un tercer grupo opcional a ARTICULO_RE
para el sufijo de palabra separado por espacio (cualquier palabra en
mayusculas, sin lista fija de sufijos latinos validos, para cubrir tambien
typos reales del propio PDF como "QUATTOUR" en vez de "QUATTUOR"). La misma
proteccion de "cita a mitad de oracion" ya usada para el resto de
ARTICULO_RE (revisar si la ultima linea de contenido cierra en '.', ':',
';' o ')') sigue aplicando sin cambios, y evita que citas como "...A QUE SE
REFIERE EL\\nARTICULO 125 NOVEM DE ESTE CAPITULO..." se traten como un
encabezado nuevo.
"""

import re
from datetime import date

from app.database import SessionLocal
from app.models import Document
from app.rag.chunker import FOOTER_RE, TRANSITORIO_RE, LegalChunk, _strip_accents
from app.rag.embeddings import embed_and_store_chunks

# Extiende el ARTICULO_RE compartido con un tercer grupo opcional para el
# sufijo ordinal latino separado por espacio (ver punto 3 del docstring del
# modulo). Los grupos (1) numero y (2) sufijo con guion "-A"/"-B" se
# mantienen identicos al ARTICULO_RE compartido.
ARTICULO_RE = re.compile(
    r"^\s*(?:ARTICULOS?|ART\.)\s+(\d+[A-Z]*)(?:-([A-Z]))?(?:\s+([A-Z]+))?"
    r"\s*[\u00b0\u00ba]?\s*[.\-]+",
    re.IGNORECASE,
)

DOCUMENT_NOMBRE = "Ley de Salud del Estado de Chiapas"

# Ruido de salto de pagina especifico de este PDF (ver punto 4 del docstring
# del modulo): numero de pagina suelto y titulo de la ley repetido al inicio
# de cada pagina. Se descartan igual que FOOTER_RE.
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")
_REPEATED_TITLE_RE = re.compile(
    r"^\s*LEY\s+DE\s+SALUD\s+DEL\s+ESTADO\s+DE\s+CHIAPAS\s*$", re.IGNORECASE
)
SOURCE_URL = (
    "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/"
    "Leyes/pdf/LEY%20DE%20SALUD%20DEL%20ESTADO%20DE%20CHIAPAS.pdf"
)
PROCESSED_TXT = "data/processed/ley_salud.txt"

# Leido del propio PDF: "ULTIMA REFORMA PUBLICADA EN EL PERIODICO OFICIAL: 7
# DE MARZO DE 2012." Publicacion original: 12 de agosto de 1998.
FECHA_PUBLICACION = date(1998, 8, 12)
FECHA_ULTIMA_REFORMA = date(2012, 3, 7)


# --- Deteccion local (mas estricta) de encabezados de Titulo/Capitulo/Seccion ---

_TITULO_LINE_RE = re.compile(r"^\s*TITULO\s+(.+?)\s*$", re.IGNORECASE)
_CAPITULO_LINE_RE = re.compile(r"^\s*CAPITULO\s+(.+?)\s*$", re.IGNORECASE)
_SECCION_LINE_RE = re.compile(r"^\s*SECCION\s+(.+?)\s*$", re.IGNORECASE)

_ORDINAL_WORD = (
    r"PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SEPTIMO|OCTAVO|NOVENO|"
    r"DECIMO|UNICO|BIS|TER|SIC|[IVXLCDM]+|\d+[A-Z]*"
)
_HEADER_LABEL_RE = re.compile(
    rf"^(?:{_ORDINAL_WORD})(?:\s+(?:{_ORDINAL_WORD}))*(?:\s*\([A-Z0-9]+\))?$",
    re.IGNORECASE,
)


def _match_header(line_re: re.Pattern, plain: str) -> str | None:
    """Devuelve el ordinal si `plain` es un encabezado real (la linea consiste
    solo en el numero/ordinal), o None si la palabra clave aparece a mitad de
    una oracion de contenido normal.
    """
    match = line_re.match(plain)
    if not match:
        return None
    label = match.group(1)
    if not _HEADER_LABEL_RE.match(label):
        return None
    return label


def chunk_ley_salud(raw_text: str, document_nombre: str) -> list[LegalChunk]:
    """Igual que app.rag.chunker.chunk_legal_text, pero con deteccion de
    Titulo/Capitulo/Seccion mas estricta (ver docstring del modulo). El manejo
    de ARTICULO/TRANSITORIO/FOOTER se reutiliza tal cual del modulo
    compartido porque no presento problemas sobre este documento (0 chunks
    sin articulo_numero, 0 numeros de articulo duplicados al validar).
    """
    lines = raw_text.splitlines()

    chunks: list[LegalChunk] = []
    current_titulo: str | None = None
    current_capitulo: str | None = None
    current_seccion: str | None = None
    current_articulo: str | None = None
    current_content: list[str] = []

    def flush() -> None:
        if current_articulo is not None and current_content:
            chunks.append(
                LegalChunk(
                    articulo_numero=current_articulo,
                    titulo=current_titulo,
                    capitulo=current_capitulo,
                    seccion=current_seccion,
                    content="\n".join(current_content).strip(),
                    document_nombre=document_nombre,
                )
            )

    for line in lines:
        plain = _strip_accents(line)

        if FOOTER_RE.match(plain):
            continue

        if _PAGE_NUMBER_RE.match(plain) or _REPEATED_TITLE_RE.match(plain):
            continue

        titulo_label = _match_header(_TITULO_LINE_RE, plain)
        if titulo_label is not None:
            flush()
            current_titulo = titulo_label
            current_articulo = None
            current_content = []
            continue

        capitulo_label = _match_header(_CAPITULO_LINE_RE, plain)
        if capitulo_label is not None:
            flush()
            current_capitulo = capitulo_label
            current_articulo = None
            current_content = []
            continue

        seccion_label = _match_header(_SECCION_LINE_RE, plain)
        if seccion_label is not None:
            flush()
            current_seccion = seccion_label
            current_articulo = None
            current_content = []
            continue

        if TRANSITORIO_RE.match(plain):
            flush()
            current_articulo = None
            current_content = []
            continue

        match = ARTICULO_RE.match(plain)
        if match:
            last_nonblank_line = next(
                (l for l in reversed(current_content) if l.strip()), ""
            )
            is_midsentence_reference = (
                current_articulo is not None
                and current_content
                and last_nonblank_line != ""
                and not last_nonblank_line.rstrip().endswith((".", ":", ";", ")"))
            )
            if is_midsentence_reference:
                current_content.append(line)
                continue

            flush()
            current_articulo = match.group(1)
            if match.group(2):
                current_articulo = f"{current_articulo}-{match.group(2)}"
            if match.group(3):
                current_articulo = f"{current_articulo} {match.group(3)}"
            current_content = [line]
            continue

        if current_articulo is not None:
            current_content.append(line)

    flush()
    return chunks


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.nombre == DOCUMENT_NOMBRE).first()
        if existing is not None:
            print(f"Documento ya existe (id={existing.id}), no se vuelve a ingerir.")
            return

        with open(PROCESSED_TXT, encoding="utf-8") as f:
            raw_text = f.read()

        legal_chunks = chunk_ley_salud(raw_text, document_nombre=DOCUMENT_NOMBRE)
        print(f"chunk_ley_salud produjo {len(legal_chunks)} chunks")
        sin_articulo = sum(1 for c in legal_chunks if c.articulo_numero is None)
        print(f"chunks sin articulo_numero: {sin_articulo}")

        numeros = [c.articulo_numero for c in legal_chunks]
        duplicados = {n for n in numeros if numeros.count(n) > 1}
        print(f"numeros de articulo duplicados: {sorted(duplicados) if duplicados else 'ninguno'}")

        document = Document(
            nombre=DOCUMENT_NOMBRE,
            tipo="ley",
            fecha_publicacion=FECHA_PUBLICACION,
            fecha_ultima_reforma=FECHA_ULTIMA_REFORMA,
            source_url=SOURCE_URL,
            area_derecho="salud",
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
