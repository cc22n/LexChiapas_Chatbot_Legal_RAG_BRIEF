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
    # Reglas 2026-11-06, de gaps medidos con 32 preguntas coloquiales (plan de
    # investigacion, seccion 13.1/13.9): la ley correcta no llegaba al primer
    # resultado porque el usuario no usa el termino legal.
    (
        re.compile(r"\b(tumb|cort|tal|derrib)\w* (un |el |los |las |mi |su )?(arbol|arboles)\b|\btala\b|\bdesmont\w+"),
        "tala de arboles aprovechamiento forestal sustentable autorizacion sanciones",
    ),
    (
        re.compile(r"pas\w+ (un |el )?(alto|semaforo)|multa\w* de transito|infraccion\w* de transito|me infraccionaron"),
        "infracciones de transito sanciones vialidad movilidad y transporte",
    ),
    (
        re.compile(r"discapacidad|discapacitad\w*|silla de ruedas"),
        "derechos de las personas con discapacidad inclusion apoyos",
    ),
    (
        re.compile(r"\b(pozo|manantial|arroyo)\b.*\bagua\b|\bagua\b.*\b(pozo|manantial)\b"),
        "aprovechamiento de aguas concesion permiso extraccion de agua",
    ),
    (
        re.compile(r"(atend\w+|trat\w+) mal.*(hospital|clinica|medico|doctor)|(hospital|clinica|medico|doctor).*(trato|atendio|atendieron) mal"),
        "derechos de los usuarios de servicios de salud queja atencion medica",
    ),
    # Reglas 2026-11-08 (plan de investigacion, 13.25): "terreno agricola junto a
    # un rio" traia Codigo Civil, Salud y Penal en vez de las leyes de suelo y
    # agua. Vocabulario tomado de los articulos reales: Ley Ambiental 184-185
    # ("descargas de aguas residuales en cuerpos o corrientes de agua") y Ley de
    # Asentamientos Humanos 72 y 76 ("areas no urbanizables ... vocacion
    # agropecuaria").
    (
        re.compile(
            r"contamin\w+ .{0,25}\b(agua|rio|arroyo|laguna|manantial)\w*|\b(agua|rio|arroyo)s? .{0,15}contamin"
            r"|\b(tir|ech|descarg|verti|arroj)\w+ .{0,40}\b(rio|arroyo|laguna|barranca|agua)\b|aguas (negras|residuales)"
        ),
        "descargas de aguas residuales en cuerpos o corrientes de agua prevencion y control de la contaminacion del agua sanciones",
    ),
    (
        re.compile(
            r"\b(terreno|zona|tierra|predio|rancho|finca)s? (de |para |con uso )?(agricola|cultivo|siembra|sembrad)\w*"
            r"|\buso agricola\b|\btierras? de (cultivo|siembra)\b|\bparcela\b"
        ),
        "areas no urbanizables vocacion agropecuaria uso de suelo programas de desarrollo urbano construccion",
    ),
    (
        re.compile(
            r"\b(licencia|permiso|autorizacion)\w* .{0,20}\b(constru\w+|edific\w+|obra)\b"
            r"|\b(constru\w+|edific\w+|levantar) .{0,25}\b(permiso|licencia|autorizacion)\w*"
        ),
        "licencia de uso de suelo y construccion autorizacion desarrollo urbano municipio",
    ),
    (
        re.compile(r"\b(orilla|ribera|margen|cerca|junto)\w* (de|del|a) (un |el |la )?(rio|arroyo|laguna)\b"),
        "cauces zonas de riesgo proteccion de cuerpos de agua ordenamiento territorial asentamientos humanos",
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
