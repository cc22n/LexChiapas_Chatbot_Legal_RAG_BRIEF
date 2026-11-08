"""Cargador generico de leyes del catalogo del Congreso de Chiapas.

Uso (desde lexchiapas/):
    python -m ingestion.load_congreso_law "CONSTITUCION POLITICA" --area constitucional           # informe (no escribe)
    python -m ingestion.load_congreso_law "CONSTITUCION POLITICA" --area constitucional --apply   # carga

Reemplaza escribir un load_ley_*.py por ley. Aplica tres compuertas ANTES de
escribir (LexChiapas_Plan_Agente_Investigacion.md, 10.1):
1. Duplicados: ni el nombre canonico ni el texto de los articulos pueden
   coincidir con un documento ya cargado (incidente real: Codigo Fiscal contra
   Codigo de la Hacienda Publica).
2. Chunking: el recorte del preambulo (indice, decreto, sentencias) debe dejar
   la ley completa, sin huecos grandes ni articulos repetidos.
3. Despues de cargar: conteo de chunks con embedding y articulos.
Sin --apply solo imprime el informe.
"""

import argparse
import re
import sys
from datetime import date

from sqlalchemy import text

from app.rag.chunker import LegalChunk, chunk_legal_text
from app.rag.text_utils import strip_accents

MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
    "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
_SMALL_WORDS = {"de", "del", "la", "las", "los", "el", "y", "e", "o", "u", "en", "para", "a", "al", "por", "con", "sobre", "que", "su", "sus", "se", "un", "una"}
_ARTICLE_ONE_RE = re.compile(r"^\s*(?i:art[ií]culo|art\.)\s*\.?\s*1\s*[°ºo]?\s*[.\-]")
_ARTICLE_TWO_RE = re.compile(r"^\s*(?i:art[ií]culo|art\.)\s*\.?\s*2\s*[°ºo]?\s*[.\-]")
_HEADING_RE = re.compile(r"^\s*(?i:libro|t[ií]tulo|cap[ií]tulo|secci[oó]n)\b")
_MARKER_DATE_RE = re.compile(r"P\.?\s*O\.?[^()]{0,60}?FECHA\s+(\d{1,2})\s+DE\s+([A-Z]+)\s+(?:DEL?\s+)?(\d{4})")
_MIN_DUPLICATE_RATIO = 0.2
_MAX_GAP_RATIO = 0.10


def canonical_name(catalog_name: str) -> str:
    """'LEY DE  VÍCTIMAS PARA EL ESTADO.' -> 'Ley de Victimas para el Estado' (ASCII, sin espacios dobles)."""
    plain = " ".join(strip_accents(catalog_name).replace(" ", " ").split()).rstrip(". ")
    words = plain.lower().split(" ")
    out = [w if (i > 0 and w in _SMALL_WORDS) else w.capitalize() for i, w in enumerate(words)]
    return " ".join(out)


def trim_to_law_start(lines: list[str]) -> int:
    """Indice de la primera linea de la ley propiamente dicha: el primer
    'Articulo 1' cuyo siguiente 'Articulo 2' (dentro de 150 lineas) no tiene
    otro 'Articulo 1' en medio (una cita suelta en un considerando no cumple),
    retrocediendo hasta 15 lineas para incluir su Libro/Titulo/Capitulo. Sirve
    para dejar fuera indice, considerandos, decretos y sentencias que traen
    algunos PDF (ej. Ley Electoral). 0 si no se encuentra."""
    ones = [i for i, l in enumerate(lines) if _ARTICLE_ONE_RE.match(l)]
    for i in ones:
        two = next((j for j in range(i + 1, min(len(lines), i + 151)) if _ARTICLE_TWO_RE.match(lines[j])), None)
        if two is None or any(i < o < two for o in ones):
            continue
        start, last_heading = i, None
        for j in range(i - 1, max(-1, i - 16), -1):
            if _HEADING_RE.match(lines[j]):
                start = last_heading = j
            elif (last_heading is None and i - j > 6) or (last_heading is not None and last_heading - j > 4):
                break
        return start
    return 0


def parse_last_reform(raw_text: str) -> date | None:
    """Fecha mas reciente entre los marcadores 'P.O. ... FECHA dd DE mes DE aaaa'."""
    found = []
    for m in _MARKER_DATE_RE.finditer(strip_accents(raw_text).upper()):
        if m.group(2) in MESES:
            try:
                found.append(date(int(m.group(3)), MESES[m.group(2)], int(m.group(1))))
            except ValueError:
                continue
    return max(found) if found else None


def _content_key(content: str) -> str:
    """Huella del cuerpo de un articulo (sin el encabezado 'Articulo N.' ni acentos/puntuacion)."""
    body = re.sub(r"^\s*(?i:art[ií]culo|art\.)\s*\.?\s*[\w\- ]{1,12}?[.\-]+\s*", "", content, count=1)
    body = re.sub(r"[^A-Z0-9 ]+", " ", strip_accents(body).upper())
    return " ".join(body.split())[:250]


def duplicate_ratio(new_chunks: list[LegalChunk], existing_keys: dict[str, str]) -> tuple[float, dict[str, int]]:
    """Fraccion de articulos nuevos cuyo cuerpo ya existe en otro documento, y a que documentos."""
    keys = [k for k in (_content_key(c.content) for c in new_chunks) if len(k) >= 60]
    if not keys:
        return 0.0, {}
    hits: dict[str, int] = {}
    for k in keys:
        doc = existing_keys.get(k)
        if doc:
            hits[doc] = hits.get(doc, 0) + 1
    return sum(hits.values()) / len(keys), hits


def numbering_report(chunks: list[LegalChunk]) -> dict:
    numbers = [c.articulo_numero for c in chunks if c.articulo_numero]
    distinct = sorted({int(m.group()) for n in numbers if (m := re.match(r"\d+", n))})
    gaps = [i for i in range(distinct[0], distinct[-1] + 1) if i not in set(distinct)] if distinct else []
    return {
        "articulos": len(set(numbers)),
        "sin_articulo": sum(1 for c in chunks if not c.articulo_numero),
        "duplicados": sorted({n for n in numbers if numbers.count(n) > 1}),
        "rango": (distinct[0], distinct[-1]) if distinct else None,
        "huecos": gaps,
        "ratio_huecos": (len(gaps) / (distinct[-1] - distinct[0] + 1)) if distinct else 1.0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga una ley del catalogo del Congreso de Chiapas")
    parser.add_argument("consulta", help="texto que identifica la ley en el catalogo (sin acentos, no distingue mayusculas)")
    parser.add_argument("--area", required=True, help="area_derecho (texto libre, ej. constitucional, administrativo, civil)")
    parser.add_argument("--tipo", default="ley")
    parser.add_argument("--nombre", help="nombre canonico (por defecto se deriva del catalogo)")
    parser.add_argument("--apply", action="store_true", help="escribe en la base (sin esto solo informa)")
    parser.add_argument("--force", action="store_true", help="ignora las compuertas de huecos")
    args = parser.parse_args(argv)

    from app.database import SessionLocal
    from app.models import Document
    from app.workers.ingestion_tasks import ingest_document
    from ingestion.parsers.pdf_parser import extract_text_from_pdf
    from ingestion.scrapers import congreso_scraper

    wanted = " ".join(strip_accents(args.consulta).upper().split())
    laws = congreso_scraper.list_available_laws()
    matches = [l for l in laws if wanted in " ".join(strip_accents(l["nombre"]).upper().split()) and "ABROGAD" not in strip_accents(l["nombre"]).upper()]
    if len(matches) > 1:
        starts = [m for m in matches if " ".join(strip_accents(m["nombre"]).upper().split()).startswith(wanted)]
        matches = starts if len(starts) == 1 else matches
    if len(matches) != 1:
        print(f"La consulta {args.consulta!r} coincide con {len(matches)} leyes (se necesita exactamente 1):")
        for m in matches[:10]:
            print("  -", m["nombre"])
        return 2
    law = matches[0]
    nombre = args.nombre or canonical_name(law["nombre"])
    print(f"Ley: {law['nombre']}\nNombre canonico: {nombre}\nURL: {law['source_url']}")

    db = SessionLocal()
    try:
        # Compuerta 1a: nombre
        existing = db.execute(text("SELECT id, nombre, is_active FROM documents")).all()
        norm = lambda s: " ".join(strip_accents(s).upper().split())
        same = [d for d in existing if norm(d.nombre) == norm(nombre) or norm(nombre) in norm(d.nombre) or norm(d.nombre) in norm(nombre)]
        if same:
            print("DUPLICADO por nombre:", [(d.id, d.nombre, d.is_active) for d in same])
            return 3

        lines = extract_text_from_pdf(congreso_scraper.download_pdf(law["source_url"])).splitlines()
        start = trim_to_law_start(lines)
        raw = "\n".join(lines[start:])
        print(f"Texto: {len(lines)} lineas; la ley empieza en la linea {start}")
        chunks = chunk_legal_text(raw, document_nombre=nombre)
        rep = numbering_report(chunks)
        print(f"Chunks: {len(chunks)} | articulos distintos: {rep['articulos']} | sin articulo: {rep['sin_articulo']} | rango: {rep['rango']} | duplicados: {rep['duplicados'][:10]} | huecos: {rep['huecos'][:15]} ({rep['ratio_huecos']:.1%})")

        # Compuerta 1b: contenido
        existing_keys: dict[str, str] = {}
        for r in db.execute(text("SELECT d.nombre, left(c.content, 600) AS c FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.is_active")):
            existing_keys.setdefault(_content_key(r.c), r.nombre)
        ratio, hits = duplicate_ratio(chunks, existing_keys)
        print(f"Articulos cuyo texto ya existe en otro documento: {ratio:.1%} {hits}")
        if ratio >= _MIN_DUPLICATE_RATIO:
            print("ABORTA: posible duplicado por contenido")
            return 3

        # Compuerta 2: chunking
        if rep["articulos"] < 3 or (rep["ratio_huecos"] > _MAX_GAP_RATIO and not args.force):
            print("ABORTA: chunking dudoso (pocos articulos o demasiados huecos); revisar o usar --force")
            return 4

        last_reform = parse_last_reform(raw)
        print(f"Ultima reforma segun marcadores: {last_reform}")
        if not args.apply:
            print("\n(informe; use --apply para cargar)")
            return 0

        document = Document(nombre=nombre, tipo=args.tipo, fecha_publicacion=None, fecha_ultima_reforma=last_reform,
                            source_url=law["source_url"], area_derecho=args.area, is_active=True)
        db.add(document)
        db.commit()
        doc_id = document.id
        db.close()
        try:
            result = ingest_document(doc_id, raw, replace_existing=False)
        except Exception:
            db = SessionLocal()
            db.execute(text("DELETE FROM documents WHERE id = :i"), {"i": doc_id})
            db.commit()
            raise
        db = SessionLocal()
        row = db.execute(text("SELECT count(*) AS n, count(embedding) AS e, min(embedding_model) AS m FROM chunks WHERE document_id = :d"), {"d": doc_id}).one()
        print(f"CARGADA: document_id={doc_id} chunks={row.n} con embedding={row.e} modelo={row.m} | {result}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
