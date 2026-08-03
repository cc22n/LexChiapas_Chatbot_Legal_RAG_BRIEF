import re

_BOLD_RE = re.compile(r"\*\*(.*?)\*\*", re.DOTALL)
_UNDERSCORE_BOLD_RE = re.compile(r"__(.*?)__", re.DOTALL)
_ITALIC_ASTERISK_RE = re.compile(r"(?<!\w)\*(.+?)\*(?!\w)", re.DOTALL)
_ITALIC_UNDERSCORE_RE = re.compile(r"(?<!\w)_(.+?)_(?!\w)", re.DOTALL)
_HEADER_RE = re.compile(r"^#{1,6}[ \t]+", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def clean_markdown(text: str) -> str:
    """Capa 2 (backend) de Fase 3.5 -- garantiza que Telegram/WhatsApp no
    muestren simbolos de Markdown crudos, sin depender de que el LLM siga
    la instruccion del system prompt (Capa 1). Opcion A del documento
    fuente: limpiar a texto plano en vez de traducir a la sintaxis propia
    de cada plataforma.
    """
    text = _BOLD_RE.sub(r"\1", text)
    text = _UNDERSCORE_BOLD_RE.sub(r"\1", text)
    text = _ITALIC_ASTERISK_RE.sub(r"\1", text)
    text = _ITALIC_UNDERSCORE_RE.sub(r"\1", text)
    text = _HEADER_RE.sub("", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    # Cualquier asterisco suelto que no formaba un par valido arriba.
    text = text.replace("*", "")
    return text
