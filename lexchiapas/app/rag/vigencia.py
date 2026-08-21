"""Deteccion de articulos COMPLETAMENTE derogados por su propio contenido
(idea 1 de 4 de la sesion de brainstorming con Perplexity, 2026-08-11 --
"vigencia real por articulo" -- ver LexChiapas_Plan_Futuro.md Fase 9).

No inventa un estado de vigencia con LLM ni depende de mantener sincronizada
una columna aparte: el corpus se scrapea de fuentes oficiales de "texto
vigente", que YA marcan un articulo derogado dejando su numero como
placeholder con contenido literal "Se Deroga" (verificado con SQL real
contra los 32 documentos activos: 38 chunks reales tienen exactamente esta
forma, ej. "Articulo 211.- Se Deroga" seguido del marcador de Periodico
Oficial). Este modulo solo reconoce ese patron ya presente en el dato real,
nunca infiere vigencia de informacion que no este en el texto.

Deliberadamente NO cubre derogacion parcial (una fraccion/parrafo derogado
dentro de un articulo que por lo demas sigue vigente, ej. Ley de Ninas
Ninos y Adolescentes Art.5 fraccion IX) -- eso es un estado intermedio
("parcialmente vigente") que este modulo no puede distinguir de forma
confiable solo con regex, y confundirlo con derogacion total seria peor que
no marcarlo (le restaria confianza a una cita que SI sigue aplicando en su
mayor parte). Ver Fase 9.2 (claim-checker) en el roadmap para el caso mas
fino de vigencia parcial."""

import re

# Tolera: con/sin acento en "Articulo", con o sin punto/guion despues del
# numero, "Se Deroga"/"Se deroga" con cualquier mayuscula/minuscula, un
# punto final opcional, y CUALQUIER cantidad de marcadores parentesis del
# Periodico Oficial antes o despues (ver extract_legal_relations.py para el
# mismo tipo de marcador) -- si al quitar el encabezado del articulo y los
# parentesis solo queda "se deroga", el articulo esta 100% derogado.
_ARTICULO_HEADER_RE = re.compile(r"^\s*Art[íi]culo\s+\S+\s*[\.\-]*\s*", re.IGNORECASE)
_PARENTHESIS_RE = re.compile(r"\([^)]*\)")
_SOLO_SE_DEROGA_RE = re.compile(r"^se\s+deroga\.?$", re.IGNORECASE)


def is_articulo_derogado(content: str) -> bool:
    """True si `content` (el texto real de un chunk) es un articulo
    COMPLETAMENTE derogado -- no queda nada mas que "Se Deroga" una vez
    quitado el encabezado ("Articulo N.-") y los marcadores del Periodico
    Oficial entre parentesis.

    Verificado contra el corpus real: 38/13307 chunks activos matchean esto
    hoy (Codigo Penal, Codigo Fiscal, Ley de Transparencia, Ley de Ninas
    Ninos y Adolescentes, Ley de Aguas)."""
    body = _ARTICULO_HEADER_RE.sub("", content, count=1)
    body = _PARENTHESIS_RE.sub("", body)
    body = body.strip().strip(".").strip()
    return bool(_SOLO_SE_DEROGA_RE.fullmatch(body))
