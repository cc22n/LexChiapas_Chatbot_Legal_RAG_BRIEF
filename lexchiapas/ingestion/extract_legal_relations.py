"""Extrae relaciones legales (reforma/deroga/adiciona) de los marcadores del
Periodico Oficial que ya estan embebidos en el texto de los chunks
ingeridos, y las guarda en la tabla `legal_relations`.

Los marcadores tienen la forma general:
    (REFORMADO, P.O. 23 DE SEPTIEMBRE DE 2009)
    (DEROGADO CON LOS ARTICULOS QUE LO INTEGRAN, POR ARTICULO TERCERO
     TRANSITORIO DE LA LEY DE ASISTENCIA E INTEGRACION DE LAS PERSONAS
     ADULTAS MAYORES DEL ESTADO DE CHIAPAS, P.O. 31 DE DICIEMBRE DE 2015)

o su familia hermana, que usa el sustantivo en vez del participio:
    (REFORMA PUBLICADA MEDIANTE P.O. NUM. 245 DE FECHA 06 DE JULIO DE 2016)
    (ADICION PUBLICADA MEDIANTE P.O. NUM. 081 DE FECHA 20 DE FEBRERO 2008)
    (DEROGACION PUBLICADA MEDIANTE P.O. NUM. 187 2A. SECCION DE FECHA
     01 DE JULIO DE 2015)

o una tercera familia, el verbo reflexivo en presente (marca fracciones
derogadas/reformadas/adicionadas dentro de un articulo, en vez del articulo
completo):
    (SE DEROGA MEDIANTE P.O. NO. 075, 2A SECCION DE FECHA 31 DE DICIEMBRE
     DE 2019)
    (SE REFORMA MEDIANTE P.O. NUM. 245 DE FECHA 06 DE JULIO DE 2016)
    (SE ADICIONA MEDIANTE P.O. NUM. 315 SEGUNDA SECCION DE FECHA 30 DE
     AGOSTO DE 2017)

El primer caso es auto-modificacion (el propio articulo de la misma ley fue
reformado en esa fecha). El segundo y tercer caso son relaciones cross-ley:
el articulo fue derogado por un articulo transitorio de OTRA ley. Las tres
familias de marcadores pueden ser cualquiera de los dos casos; el criterio
de auto-modificacion vs cross-ley se aplica igual para las tres.

HALLAZGO REAL (2026-07-28, al investigar 2 variantes puntuales pedidas --
"SE DEROGA PUBLICADA", "REFORMADA [N. DE E. REPUBLICADA]" -- que resultaron
ser solo 2 casos de dos familias MUCHO mas grandes que no estaban cubiertas
en absoluto): el participio de la familia 1 solo reconocia la forma
MASCULINA (DEROGADO/REFORMADO/ADICIONADO) -- la forma FEMENINA (DEROGADA/
REFORMADA/ADICIONADA, que aparece cuando el marcador se refiere a una
fraccion/seccion/denominacion, sustantivos femeninos, en vez de un articulo)
tiene 295 ocurrencias reales en el corpus sin extraer. La familia 3 (verbo
reflexivo "SE <verbo>") tiene otras 141 ocurrencias reales, tampoco
cubiertas por ninguna de las dos familias anteriores (ni el participio
-"DEROGADO"/"DEROGADA"- ni el sustantivo pegado a la apertura del parentesis
-"DEROGACION"- aparecen en "SE DEROGA"). Verificado con SQL real contra
todos los chunks activos antes de escribir el fix (conteo por familia,
sin overlap entre las tres). 436 relaciones nuevas sobre 2017 ya existentes
(~20% de crecimiento del grafo).

Idempotente: trunca `legal_relations` al inicio (TRUNCATE ... RESTART
IDENTITY) antes de volver a poblarla, asi que correr el script varias veces
no duplica filas -- siempre refleja el estado actual de `chunks`.

No modifica chunks, documents, ni ningun otro modulo del pipeline RAG.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

from sqlalchemy import text

from app.database import SessionLocal
from app.models import Chunk, Document, LegalRelation

# Patron principal: cualquier parentesis que contenga al menos una de las
# palabras clave del Periodico Oficial (participio, masculino o femenino --
# la forma femenina aplica cuando el marcador califica una fraccion/seccion/
# denominacion en vez de un articulo, ej. "(REFORMADA SU DENOMINACION, P.O.
# ...)" -- mismo evento real, solo concordancia de genero distinta, ver
# HALLAZGO REAL en el docstring del modulo). [^)] tambien matchea saltos de
# linea (el texto de los PDFs a veces envuelve el marcador en varias
# lineas), por eso se normaliza whitespace despues de extraer el match.
MARKER_RE = re.compile(
    r"\([^)]*(?:DEROGADO|DEROGADA|REFORMADO|REFORMADA|ADICIONADO|ADICIONADA)[^)]*\)",
    re.IGNORECASE,
)

KEYWORD_RE = re.compile(r"DEROGADO|DEROGADA|REFORMADO|REFORMADA|ADICIONADO|ADICIONADA", re.IGNORECASE)

RELATION_TYPE_BY_KEYWORD = {
    "DEROGADO": "deroga",
    "DEROGADA": "deroga",
    "REFORMADO": "reforma",
    "REFORMADA": "reforma",
    "ADICIONADO": "adiciona",
    "ADICIONADA": "adiciona",
}

# Patron hermano: "(REFORMA PUBLICADA MEDIANTE P.O. ...)",
# "(ADICION PUBLICADA ...)", "(DEROGACION PUBLICADA ...)" -- mismo tipo de
# marcador del Periodico Oficial pero con el sustantivo (sin el sufijo
# "-DO"/"-DA") en vez del participio, seguido de la palabra "PUBLICAD..."
# (PUBLICADA/Publicada, tolerante a mayus/minus via IGNORECASE).
#
# El requisito de que el sustantivo aparezca pegado a la apertura del
# parentesis ("\(\s*(?:...)\s+PUBLICAD") es intencional: excluye el
# marcador "(ULTIMA REFORMA PUBLICADA MEDIANTE P.O. ...)" que aparece
# repetido como pie de pagina/estampa de "ultima reforma del documento
# completo" en decenas de articulos y NO es un evento de modificacion de
# ese articulo especifico -- incluirlo generaria relaciones falsas (una
# por cada articulo del documento en vez de una por cada reforma real).
#
# En el corpus real "ADICION"/"DEROGACION" a veces llevan acento (letra O
# con acento agudo) y a veces no. En vez de meter el caracter acentuado
# literal en el regex (rompiendo la convencion de codigo fuente ASCII
# puro), se hace un "fold" de una COPIA del texto del chunk antes de
# buscar (ver fold_accents_preserve_length) que reemplaza esa letra
# acentuada por su equivalente sin acento preservando la longitud/
# posicion exacta de cada caracter, asi el regex de abajo solo necesita
# reconocer ASCII plano y los indices de match siguen siendo validos
# para recortar el texto ORIGINAL (con acento real) del chunk.
MARKER_RE_PUBLICADA = re.compile(
    r"\(\s*(?:REFORMA|ADICION|DEROGACION)\s+PUBLICAD[^)]*\)",
    re.IGNORECASE,
)

PUBLICADA_KEYWORD_RE = re.compile(r"REFORMA|ADICION|DEROGACION", re.IGNORECASE)

RELATION_TYPE_BY_PUBLICADA_PREFIX = {
    "REFORMA": "reforma",
    "ADICION": "adiciona",
    "DEROGACION": "deroga",
}

# Tabla de "fold" de acentos: mapea el codepoint de "O con acento agudo"
# (mayuscula y minuscula) a la "O" simple equivalente, construida via
# ord()/chr() con codepoints numericos para no tener que escribir el
# caracter acentuado literal en el archivo fuente. Se limita a la letra
# que de hecho aparece en los marcadores de este corpus (ADICION/
# DEROGACION); si el corpus llegara a usar otras vocales acentuadas en
# estos marcadores especificos, se agregarian aqui de la misma forma.
_O_ACUTE_UPPER = chr(0xD3)  # letra O mayuscula con acento agudo
_O_ACUTE_LOWER = chr(0xF3)  # letra o minuscula con acento agudo
ACCENT_FOLD_MAP = {
    ord(_O_ACUTE_UPPER): ord("O"),
    ord(_O_ACUTE_LOWER): ord("o"),
}


def fold_accents_preserve_length(s: str) -> str:
    """Reemplaza (1 caracter por 1 caracter, sin cambiar longitud ni
    posiciones) las vocales acentuadas relevantes por su version sin
    acento, para poder correr regex ASCII-only sobre el resultado y
    despues recortar el texto ORIGINAL usando los mismos indices de
    match."""
    return s.translate(ACCENT_FOLD_MAP)


def parse_relation_type_publicada(folded_marker_text: str) -> str | None:
    """Relation type para la familia "PUBLICADA": toma la primera palabra
    clave (REFORMA/ADICION/DEROGACION) del texto YA FOLDEADO (sin acentos)
    y la mapea al mismo relation_type que su contraparte participio."""
    m = PUBLICADA_KEYWORD_RE.search(folded_marker_text)
    if not m:
        return None
    return RELATION_TYPE_BY_PUBLICADA_PREFIX.get(m.group(0).upper())


# Familia 3: verbo reflexivo en presente -- "(SE DEROGA MEDIANTE P.O. ...)",
# "(SE REFORMA MEDIANTE P.O. ...)", "(SE ADICIONA MEDIANTE/ESTE CAPITULO
# P.O. ...)". El requisito de que "SE <verbo>" aparezca pegado a la
# apertura del parentesis (misma razon que MARKER_RE_PUBLICADA) evita
# matchear texto narrativo suelto que mencione estas palabras sin ser una
# cita real del Periodico Oficial. El conector entre el verbo y "P.O."
# varia libremente en el corpus real (MEDIANTE, PUBLICADA EN EL, ESTE
# CAPITULO, o directo) -- por eso [^)]* despues del verbo en vez de un
# conector fijo, igual de tolerante que el resto de los patrones de este
# archivo. "ADICONA" (sin la segunda "I") es un typo real repetido 3 veces
# en el corpus, se tolera igual que otros typos ya documentados en este
# modulo (ver fold_accents_preserve_length para el precedente).
MARKER_RE_SE_VERBO = re.compile(
    r"\(\s*SE\s+(?:DEROGA|REFORMA|ADICIONA|ADICONA)\b[^)]*\)",
    re.IGNORECASE,
)

SE_VERBO_KEYWORD_RE = re.compile(r"DEROGA|REFORMA|ADICIONA|ADICONA", re.IGNORECASE)

RELATION_TYPE_BY_SE_VERBO = {
    "DEROGA": "deroga",
    "REFORMA": "reforma",
    "ADICIONA": "adiciona",
    "ADICONA": "adiciona",
}


def parse_relation_type_se_verbo(marker_text: str) -> str | None:
    """Relation type para la familia "SE <verbo>" -- misma logica que
    parse_relation_type_publicada, sin necesitar fold de acentos (ninguna
    de estas 4 palabras clave lleva tilde en el corpus real)."""
    m = SE_VERBO_KEYWORD_RE.search(marker_text)
    if not m:
        return None
    return RELATION_TYPE_BY_SE_VERBO.get(m.group(0).upper())


MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# "P.O. 23 DE SEPTIEMBRE DE 2009" / "P.O. NUM. 113 DE FECHA 28 DE AGOSTO
# 2008" (sin "DE" antes del anio) / "P. O. No 389 de fecha 17 de Septiembre
# de 2012" (minusculas, "P. O." con espacio). No dependemos de que "P.O."
# se reconozca de forma exacta -- basta con localizar el patron
# "<dia> DE <mes> [DE] <anio>" que es estable en todas las variantes vistas
# en el corpus real.
DATE_RE = re.compile(
    r"(\d{1,2})\s+(?:DEL?\s+)?"
    r"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|SETIEMBRE"
    r"|OCTUBRE|NOVIEMBRE|DICIEMBRE)\.?\s*(?:DEL?\s+)?(\d{4})",
    re.IGNORECASE,
)

# Palabras que, si aparecen despues de "POR" dentro del marcador, indican
# que se esta nombrando a OTRA ley/codigo/reglamento/constitucion (relacion
# cross-ley) en vez de una auto-modificacion.
CROSSLAW_KEYWORD_RE = re.compile(
    r"DE LA LEY|DEL C[O0]DIGO|DE LA CONSTITUCI[O0]N|DEL REGLAMENTO",
    re.IGNORECASE,
)

PO_TOKEN_RE = re.compile(r",?\s*P\.?\s*O\.?", re.IGNORECASE)

FUZZY_MATCH_THRESHOLD = 0.82


def normalize_ws(s: str) -> str:
    """Colapsa cualquier corrida de whitespace (incluyendo saltos de linea
    dentro de un marcador envuelto en el PDF) a un solo espacio."""
    return re.sub(r"\s+", " ", s).strip()


def normalize_for_match(s: str) -> str:
    """Quita acentos, sube a mayusculas y colapsa puntuacion/espacios para
    comparar nombres de leyes de forma tolerante a diferencias de
    encoding/acentos entre el texto del marcador y documents.nombre."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return " ".join(s.split())


def parse_relation_type(marker_text: str) -> str | None:
    """Relation type = la primera palabra clave (DEROGADO/REFORMADO/
    ADICIONADO) que aparece en el texto del marcador, por posicion."""
    m = KEYWORD_RE.search(marker_text)
    if not m:
        return None
    return RELATION_TYPE_BY_KEYWORD[m.group(0).upper()]


def parse_fecha(marker_text: str) -> date | None:
    m = DATE_RE.search(marker_text)
    if not m:
        return None
    dia_s, mes_s, anio_s = m.groups()
    mes_num = MESES.get(mes_s.lower())
    if mes_num is None:
        return None
    try:
        return date(int(anio_s), mes_num, int(dia_s))
    except ValueError:
        # dia invalido (ej. 31 de febrero) -- no deberia pasar en el
        # corpus real, pero si pasa preferimos None a un dato incorrecto.
        return None


def extract_crosslaw_name(marker_text: str) -> str | None:
    """Si el marcador nombra a otra ley/codigo/reglamento/constitucion
    despues de la palabra "POR", devuelve el nombre extraido (sin el
    "DE LA "/"DEL " que lo antecede). Si no, devuelve None (auto-
    modificacion)."""
    upper = marker_text.upper()
    por_idx = upper.find("POR")
    if por_idx == -1:
        return None

    m = CROSSLAW_KEYWORD_RE.search(marker_text, por_idx)
    if not m:
        return None

    kw_upper = m.group(0).upper()
    if kw_upper.startswith("DE LA "):
        name_start = m.start() + len("DE LA ")
    elif kw_upper.startswith("DEL "):
        name_start = m.start() + len("DEL ")
    else:
        name_start = m.start()

    po_match = PO_TOKEN_RE.search(marker_text, name_start)
    name_end = po_match.start() if po_match else len(marker_text)

    name = marker_text[name_start:name_end].strip().strip(",").strip()
    return name or None


def best_document_match(law_name: str, documents: list[Document]) -> Document | None:
    """Fuzzy match tolerante a acentos/mayusculas contra documents.nombre.
    No exige match perfecto: exacto tras normalizar, o contains en
    cualquier direccion, o similitud de secuencia >= FUZZY_MATCH_THRESHOLD."""
    n_law = normalize_for_match(law_name)
    best_doc = None
    best_score = 0.0
    for doc in documents:
        n_doc = normalize_for_match(doc.nombre)
        if n_law == n_doc:
            score = 1.0
        elif n_doc in n_law or n_law in n_doc:
            score = 0.95
        else:
            score = SequenceMatcher(None, n_law, n_doc).ratio()
        if score > best_score:
            best_score = score
            best_doc = doc
    if best_score >= FUZZY_MATCH_THRESHOLD:
        return best_doc
    return None


def build_relation(
    *,
    document_id: int,
    chunk_id: int,
    articulo_numero: str | None,
    from_doc: Document,
    documents: list[Document],
    relation_type: str,
    raw_marker: str,
    extraction_method: str,
    counters: dict[str, int],
) -> LegalRelation:
    """Construye (sin insertar) una fila de LegalRelation a partir de un
    marcador ya identificado, aplicando la misma logica de fecha y
    cross-ley/auto-modificacion para ambas familias de marcadores."""
    marker_text = normalize_ws(raw_marker)

    fecha = parse_fecha(marker_text)
    if fecha is None:
        counters["skipped_no_date"] += 1

    crosslaw_name = extract_crosslaw_name(marker_text)
    if crosslaw_name:
        to_law_name_raw = crosslaw_name
        matched_doc = best_document_match(crosslaw_name, documents)
        if matched_doc is not None:
            to_document_id = matched_doc.id
            counters["cross_resolved"] += 1
        else:
            to_document_id = None
            counters["cross_unresolved"] += 1
    else:
        to_law_name_raw = from_doc.nombre
        to_document_id = from_doc.id
        counters["auto_mod"] += 1

    return LegalRelation(
        from_document_id=document_id,
        from_chunk_id=chunk_id,
        from_articulo=articulo_numero,
        relation_type=relation_type,
        to_document_id=to_document_id,
        to_law_name_raw=to_law_name_raw,
        fecha=fecha,
        source_text=raw_marker,
        extraction_method=extraction_method,
    )


def main() -> None:
    db = SessionLocal()
    try:
        documents = db.query(Document).filter(Document.is_active.is_(True)).all()
        doc_by_id = {d.id: d for d in documents}

        rows = db.execute(
            text(
                """
                SELECT c.id, c.document_id, c.articulo_numero, c.content
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.is_active = true
                """
            )
        ).fetchall()
        print(f"chunks activos consultados: {len(rows)}")

        # Idempotencia: siempre repoblar desde cero a partir del estado
        # actual de chunks, en vez de intentar deduplicar fila por fila.
        db.execute(text("TRUNCATE TABLE legal_relations RESTART IDENTITY"))
        db.commit()

        counters = {
            "skipped_no_date": 0,
            "cross_resolved": 0,
            "cross_unresolved": 0,
            "auto_mod": 0,
        }
        inserted = 0
        inserted_publicada = 0
        inserted_se_verbo = 0
        skipped_no_type = 0

        for chunk_id, document_id, articulo_numero, content in rows:
            from_doc = doc_by_id.get(document_id)
            if from_doc is None:
                continue

            # --- Familia 1: (REFORMADO ...), (DEROGADO ...), (ADICIONADO ...)
            for match in MARKER_RE.finditer(content):
                raw_marker = match.group(0)
                marker_text = normalize_ws(raw_marker)

                relation_type = parse_relation_type(marker_text)
                if relation_type is None:
                    skipped_no_type += 1
                    continue

                relation = build_relation(
                    document_id=document_id,
                    chunk_id=chunk_id,
                    articulo_numero=articulo_numero,
                    from_doc=from_doc,
                    documents=documents,
                    relation_type=relation_type,
                    raw_marker=raw_marker,
                    extraction_method="regex",
                    counters=counters,
                )
                db.add(relation)
                inserted += 1

            # --- Familia 2 (hermana): (REFORMA PUBLICADA ...),
            # (ADICION PUBLICADA ...), (DEROGACION PUBLICADA ...). Se corre
            # sobre una copia "foldeada" (sin acentos, misma longitud) del
            # contenido del chunk para poder usar un regex ASCII-only y
            # luego recortar el texto ORIGINAL (con acento real) usando los
            # mismos indices de match -- ver fold_accents_preserve_length.
            content_folded = fold_accents_preserve_length(content)
            for match in MARKER_RE_PUBLICADA.finditer(content_folded):
                raw_marker = content[match.start():match.end()]
                folded_marker_text = normalize_ws(match.group(0))

                relation_type = parse_relation_type_publicada(folded_marker_text)
                if relation_type is None:
                    skipped_no_type += 1
                    continue

                relation = build_relation(
                    document_id=document_id,
                    chunk_id=chunk_id,
                    articulo_numero=articulo_numero,
                    from_doc=from_doc,
                    documents=documents,
                    relation_type=relation_type,
                    raw_marker=raw_marker,
                    extraction_method="regex_publicada",
                    counters=counters,
                )
                db.add(relation)
                inserted += 1
                inserted_publicada += 1

            # --- Familia 3: (SE DEROGA ...), (SE REFORMA ...),
            # (SE ADICIONA ...) -- ver MARKER_RE_SE_VERBO arriba. Ninguna de
            # sus palabras clave lleva tilde en el corpus real, corre sobre
            # el contenido ORIGINAL (sin fold).
            for match in MARKER_RE_SE_VERBO.finditer(content):
                raw_marker = match.group(0)
                marker_text = normalize_ws(raw_marker)

                relation_type = parse_relation_type_se_verbo(marker_text)
                if relation_type is None:
                    skipped_no_type += 1
                    continue

                relation = build_relation(
                    document_id=document_id,
                    chunk_id=chunk_id,
                    articulo_numero=articulo_numero,
                    from_doc=from_doc,
                    documents=documents,
                    relation_type=relation_type,
                    raw_marker=raw_marker,
                    extraction_method="regex_se_verbo",
                    counters=counters,
                )
                db.add(relation)
                inserted += 1
                inserted_se_verbo += 1

        db.commit()

        print(f"relaciones insertadas (total): {inserted}")
        print(f"  de las cuales familia 'PUBLICADA' (nuevas en esta pasada): {inserted_publicada}")
        print(f"  de las cuales familia 'SE VERBO' (nuevas en esta pasada): {inserted_se_verbo}")
        print(f"marcadores sin palabra clave reconocida (omitidos): {skipped_no_type}")
        print(f"marcadores sin fecha parseable (insertados con fecha=NULL): {counters['skipped_no_date']}")
        print(f"auto-modificacion (misma ley): {counters['auto_mod']}")
        print(f"cross-ley resuelta a otro documento: {counters['cross_resolved']}")
        print(f"cross-ley sin resolver (to_document_id NULL): {counters['cross_unresolved']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
