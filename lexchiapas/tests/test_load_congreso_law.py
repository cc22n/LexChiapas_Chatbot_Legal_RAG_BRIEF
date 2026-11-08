"""Cargador generico de leyes del Congreso: funciones puras (sin red ni base de datos)."""

from datetime import date

from app.rag.chunker import LegalChunk
from ingestion.load_congreso_law import (
    canonical_name,
    duplicate_ratio,
    numbering_report,
    parse_last_reform,
    trim_to_law_start,
    _content_key,
)


def test_canonical_name_is_ascii_title_case_without_double_spaces():
    assert canonical_name("LEY DE  V\u00cdCTIMAS PARA EL ESTADO DE CHIAPAS") == "Ley de Victimas para el Estado de Chiapas"
    assert canonical_name("CONSTITUCI\u00d3N POL\u00cdTICA DEL ESTADO LIBRE Y SOBERANO DE CHIAPAS.") == "Constitucion Politica del Estado Libre y Soberano de Chiapas"
    assert canonical_name("LEY ORG\u00c1NICA DEL TRIBUNAL  DE JUSTICIA") == "Ley Organica del Tribunal de Justicia"


def test_trim_skips_index_and_quoted_articles_and_keeps_the_book_heading():
    lines = (
        ["CONSIDERANDO", "Articulo 1. cita aislada en un considerando", "texto", "Libro Primero. Indice"]
        + ["relleno"] * 5
        + ["Libro Primero", "Titulo Unico", "Capitulo I", "Articulo 1.", "Texto uno.", "Articulo 2.", "Texto dos."]
    )
    start = trim_to_law_start(lines)
    assert lines[start] == "Libro Primero" and start == 9


def test_trim_returns_zero_when_no_article_sequence_found():
    assert trim_to_law_start(["solo texto", "sin articulos"]) == 0


def test_parse_last_reform_takes_the_latest_marker():
    raw = "(REFORMADO, P.O. NUM. 12 DE FECHA 03 DE SEPTIEMBRE DE 2026)\n(ADICIONADO, P.O. 1 DE FECHA 14 DE ENERO DEL 2019)"
    assert parse_last_reform(raw) == date(2026, 9, 3)
    assert parse_last_reform("sin marcadores") is None


def _chunk(num, content):
    return LegalChunk(articulo_numero=num, titulo=None, capitulo=None, seccion=None, content=content)


def test_numbering_report_flags_gaps_duplicates_and_missing_numbers():
    chunks = [_chunk("1", "a"), _chunk("2", "b"), _chunk("4", "c"), _chunk("4", "d"), _chunk(None, "e")]
    rep = numbering_report(chunks)
    assert rep["huecos"] == [3] and rep["duplicados"] == ["4"] and rep["sin_articulo"] == 1 and rep["rango"] == (1, 4)


def test_duplicate_ratio_detects_text_already_present_elsewhere():
    body = "Las disposiciones de esta Ley son de orden publico y de observancia general en todo el territorio del Estado de Chiapas."
    existing = {_content_key("Articulo 1.\n" + body): "Otra Ley"}
    same = [_chunk("1", "Art\u00edculo 1. " + body)]
    other = [_chunk("1", "Articulo 1. Este texto no se parece a nada de lo ya cargado y trata de otro tema completamente distinto aqui.")]
    assert duplicate_ratio(same, existing)[0] == 1.0
    assert duplicate_ratio(other, existing)[0] == 0.0
