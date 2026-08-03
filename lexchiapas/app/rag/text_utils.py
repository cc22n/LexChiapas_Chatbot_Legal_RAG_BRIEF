import unicodedata


def strip_accents(text: str) -> str:
    """Usado por modulos de app/rag que necesitan comparar texto en espanol
    contra patrones ASCII (convencion del proyecto: codigo fuente ASCII
    puro, ver CLAUDE.md) sin depender de que el texto de entrada ya venga
    sin acentos (respuestas de LLM, preguntas de usuario)."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))
