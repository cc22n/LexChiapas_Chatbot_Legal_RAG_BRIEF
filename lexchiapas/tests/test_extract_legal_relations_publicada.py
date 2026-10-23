from datetime import date

from ingestion.extract_legal_relations import (
    fold_accents_preserve_length,
    iter_publicada_markers,
    normalize_ws,
    parse_fecha,
    parse_relation_type_publicada,
)


def _markers(text: str) -> list[str]:
    folded = fold_accents_preserve_length(text)
    return [m.group(0).strip() for m in iter_publicada_markers(folded)]


def test_marker_with_opening_paren_still_matches():
    text = "ARTICULO 1.- TEXTO.\n(REFORMA PUBLICADA EN EL P. O. NUM. 274, DE FECHA 31 DE DICIEMBRE DE 2016.)"
    assert len(_markers(text)) == 1


def test_marker_missing_opening_paren_at_line_start_matches():
    # Errata real del PDF del Congreso (Ley del Servicio Civil, art. 149).
    text = (
        "ARTICULO 149.- LAS PRESUNCIONES LEGALES ADMITEN PRUEBA EN CONTRARIO.\n"
        "ADICION PUBLICADA EN EL P. O. NUM. 274-2A. SECCION, DE FECHA 31 DE DICIEMBRE DE 2016.)"
    )
    found = _markers(text)
    assert len(found) == 1
    marker_text = normalize_ws(found[0])
    assert parse_relation_type_publicada(marker_text) == "adiciona"
    assert parse_fecha(marker_text) == date(2016, 12, 31)


def test_footer_with_paren_is_not_a_marker():
    # "(ULTIMA REFORMA PUBLICADA ...)": la palabra clave no esta pegada al "(".
    text = "(ULTIMA REFORMA PUBLICADA MEDIANTE P.O. NUM. 1, DE FECHA 1 DE ENERO DE 2020)"
    assert _markers(text) == []


def test_footer_split_across_lines_is_not_a_marker():
    # El pie partido en dos lineas dejaria "REFORMA PUBLICADA ..." al inicio de linea.
    text = "(ULTIMA\nREFORMA PUBLICADA MEDIANTE P.O. NUM. 1, DE FECHA 1 DE ENERO DE 2020)"
    assert _markers(text) == []


def test_keyword_mid_line_without_paren_is_not_a_marker():
    text = "SEGUN LA REFORMA PUBLICADA EN EL DIARIO OFICIAL EL 5 DE MAYO DE 2010) SE APLICA"
    assert _markers(text) == []


def test_line_start_keyword_without_closing_paren_nearby_does_not_overconsume():
    # Prosa que abre linea con "REFORMA PUBLICADA" y cuyo ")" esta a >250 caracteres.
    text = "REFORMA PUBLICADA " + ("TEXTO LARGO SIN PARENTESIS " * 20) + ")"
    assert _markers(text) == []
