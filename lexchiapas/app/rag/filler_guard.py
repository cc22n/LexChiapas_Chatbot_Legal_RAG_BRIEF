"""Detector de frases de relleno (LexChiapas_Plan_Agente_Investigacion.md, 13.5-13.6).

Caso real: "como se constituye una sociedad anonima". El generador admite que
los fragmentos no contienen informacion sobre lo preguntado, cita un articulo
cercano (el del contrato de sociedad civil) y luego completa con conocimiento
propio ("para constituir una sociedad anonima, generalmente se requiere un acta
constitutiva..."), lo que viola la regla de contenido (solo fragmentos). El
segundo gate lo da por fundamentado porque el tema (sociedad) es el mismo.

Regla (heuristica sin llamadas LLM): si la respuesta ADMITE falta de
informacion y ademas usa un adverbio de generalidad ("generalmente",
"normalmente"...), esas frases son relleno: se eliminan y la respuesta deja de
contar como fundamentada. Medida sobre 190 respuestas reales: 2 detecciones
(las dos de sociedad anonima) y 0 falsos positivos en 98 respuestas de
positivos. Limite conocido: solo cubre la lista de adverbios de abajo.
"""

import re

from app.rag.text_utils import strip_accents

# Admision explicita de falta de informacion (texto ya sin acentos y en minusculas).
_ADMIT_RE = re.compile(
    r"\bno (hay|tengo|contiene|contienen|existe|existen|se encontro|se encontraron|encontre|"
    r"cuento con|incluye|incluyen|especifica|especifican|aparece|aparecen|menciona|mencionan)\b"
    r"[^.]{0,60}\b(informacion|datos|articulos?|disposiciones|detalles|fragmentos|especific\w*)"
)

# Solo adverbios inequivocos de "lo que suele pasar". Se dejan fuera
# "en general" y "en la practica": aparecen tambien en frases fundamentadas.
_FILLER_RE = re.compile(
    r"\b(generalmente|normalmente|usualmente|habitualmente|por lo general|tipicamente|"
    r"suele|suelen|comunmente|por lo regular)\b"
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_SPLIT_RE = re.compile(r"(\n\s*\n)")


def _norm(text: str) -> str:
    return strip_accents(text).lower()


def strip_unsupported_filler(answer: str) -> tuple[str, bool]:
    """Devuelve (respuesta_limpia, hubo_relleno).

    `hubo_relleno` es True solo si la respuesta admite falta de informacion Y
    contiene alguna frase de relleno; entonces el llamador debe tratarla como
    NO fundamentada. Las frases con relleno se quitan conservando los saltos
    de parrafo. Si quitarlas dejara la respuesta vacia, se devuelve el texto
    original (igual se reporta el relleno).
    """
    if not answer:
        return answer, False
    normalized = _norm(answer)
    if not (_ADMIT_RE.search(normalized) and _FILLER_RE.search(normalized)):
        return answer, False

    cleaned_parts: list[str] = []
    for part in _PARAGRAPH_SPLIT_RE.split(answer):
        if _PARAGRAPH_SPLIT_RE.fullmatch(part):
            cleaned_parts.append(part)
            continue
        kept = [s for s in _SENTENCE_SPLIT_RE.split(part) if not _FILLER_RE.search(_norm(s))]
        cleaned_parts.append(" ".join(kept))

    # Colapsar parrafos que quedaron vacios junto con su separador.
    out: list[str] = []
    for part in cleaned_parts:
        if _PARAGRAPH_SPLIT_RE.fullmatch(part):
            out.append(part)
        elif part.strip():
            out.append(part)
        elif out and _PARAGRAPH_SPLIT_RE.fullmatch(out[-1]):
            out.pop()
    cleaned = "".join(out).strip()
    return (cleaned if cleaned else answer), True
