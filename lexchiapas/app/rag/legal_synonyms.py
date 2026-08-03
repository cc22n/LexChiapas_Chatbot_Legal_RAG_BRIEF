import re

from app.rag.text_utils import strip_accents

# Fase 3.7, hallazgo real (investigacion del caso Art.1576, Codigo Civil
# Libro Tercero, "quien hereda sin testamento"): el articulo que define
# QUIENES heredan (Art.1576, "TIENEN DERECHO A HEREDAR POR SUCESION
# LEGITIMA") nunca usa la palabra "testamento" en su propio texto -- esa
# conexion vive en el Art.1573, dos articulos antes, en un chunk separado
# sin traslape lexico. El titulo bajo el que vive (TITULO CUARTO, "DE LA
# SUCESION LEGITIMA") tampoco se incluye en el texto que se embebe. Medido
# en vivo: Art.1576 solo llegaba a similitud 0.4765 (posicion #1141 de 7746
# chunks) contra la pregunta coloquial "quien hereda sin testamento".
#
# Fix elegido (el barato de los dos evaluados con el usuario): expandir la
# consulta de BUSQUEDA con el termino legal real ANTES de embeber, sin
# tocar el corpus ni re-embeber los 7746 chunks existentes. Reglas
# deterministas (sin LLM, sin latencia extra real) -- se agregan mas
# entradas aqui a medida que se confirmen nuevos gaps semanticos reales
# (no se inventan reglas para casos no medidos).
#
# "sin testamento" mezcla en realidad DOS conceptos legales distintos que
# viven en articulos separados: (1) la condicion que abre la sucesion
# legitima (Art.1573: "CUANDO NO HAY TESTAMENTO...") y (2) quienes tienen
# derecho a heredar bajo esa sucesion (Art.1576: "TIENEN DERECHO A HEREDAR
# POR SUCESION LEGITIMA: LOS DESCENDIENTES, CONYUGE..."). Primera version
# de esta regla solo cubria el concepto (1) -- medido en vivo, subio el
# Art.1573 de no aparecer en el top-30 a la posicion #1, pero el Art.1576
# seguia sin entrar (ni por dense ni por BM25, el termino "sucesion
# legitima" es demasiado comun en todo el Libro Tercero para discriminarlo
# por si solo). Se agrega "quienes tienen derecho a heredar" -- frase
# juridica estandar (no una paletizacion literal del articulo especifico,
# es como los codigos civiles mexicanos formulan este concepto en general)
# para cubrir tambien el concepto (2).
_SYNONYM_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"sin testamento|sin dejar testamento|muer\w* intestad\w*|fallec\w* intestad\w*|\bintestad\w*\b"),
        "sucesion legitima quienes tienen derecho a heredar orden de herederos",
    ),
]


def expand_legal_synonyms(question: str) -> tuple[str, bool]:
    """Devuelve (consulta_para_buscar, se_expandio).

    Solo agrega terminos AL FINAL de la consulta de busqueda (nunca
    reemplaza el texto original, nunca toca la pregunta que ve el usuario
    ni el prompt de generacion) -- es una ayuda para el embedding de
    busqueda, no una reescritura semantica como app.rag.query_rewriting.
    Si ninguna regla aplica, devuelve la pregunta sin cambios.
    """
    clean = strip_accents(question.lower())
    additions = [expansion for pattern, expansion in _SYNONYM_RULES if pattern.search(clean)]
    if not additions:
        return question, False
    return question + " " + " ".join(additions), True
