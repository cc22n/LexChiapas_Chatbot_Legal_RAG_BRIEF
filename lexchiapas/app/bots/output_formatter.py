import re

_BOLD_RE = re.compile(r"\*\*(.*?)\*\*", re.DOTALL)
_UNDERSCORE_BOLD_RE = re.compile(r"__(.*?)__", re.DOTALL)
_ITALIC_ASTERISK_RE = re.compile(r"(?<!\w)\*(.+?)\*(?!\w)", re.DOTALL)
_ITALIC_UNDERSCORE_RE = re.compile(r"(?<!\w)_(.+?)_(?!\w)", re.DOTALL)
_HEADER_RE = re.compile(r"^#{1,6}[ \t]+", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_CODE_FENCE_RE = re.compile(r"```[a-zA-Z]*\n?(.*?)```", re.DOTALL)

# Fase 1 (contenido visual, 2026-08-07): con visual_answers.comparison_tables
# encendida (ver app.rag.generator), el LLM puede armar tablas markdown --
# SYSTEM_PROMPT es compartido por los dos canales, asi que Telegram tambien
# las recibe. Telegram no renderiza tablas NUNCA (no es HTML/markdown real,
# es su propio subset limitado sin soporte de tablas), asi que flatten_
# markdown_tables las aplana a texto legible en vez de dejar pipes crudos.
# Una linea separadora real ("|---|---|", solo pipes/guiones/dos
# puntos/espacios) es la senal de que la fila anterior fue un encabezado de
# tabla de verdad -- sin esa confirmacion, texto normal que use "|" (poco
# comun pero posible) no se toca.
_TABLE_SEPARATOR_RE = re.compile(r"^\|?[\s:|-]+\|?$")


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def flatten_markdown_tables(text: str) -> str:
    """Convierte cada tabla markdown GFM en parrafos "Celda1: Encabezado:
    valor; Encabezado: valor" -- uno por fila, en vez de pipes crudos.
    Ejemplo real esperado: "Ley de Salud, Art. 45: Sancion: multa de 50 UMA;
    Autoridad: Secretaria de Salud".
    """
    lines = text.split("\n")
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        is_table_start = (
            len(stripped) >= 2
            and stripped.startswith("|")
            and stripped.endswith("|")
            and i + 1 < len(lines)
            and bool(_TABLE_SEPARATOR_RE.match(lines[i + 1].strip()))
        )
        if not is_table_start:
            result.append(line)
            i += 1
            continue

        headers = _split_table_row(line)
        i += 2  # salta encabezado + linea separadora
        while i < len(lines):
            row_stripped = lines[i].strip()
            if not (row_stripped.startswith("|") and row_stripped.endswith("|")):
                break
            cells = _split_table_row(lines[i])
            first_cell = cells[0] if cells else ""
            rest = "; ".join(
                f"{header}: {value}" for header, value in zip(headers[1:], cells[1:])
            )
            result.append(f"{first_cell}: {rest}" if rest else first_cell)
            i += 1
    return "\n".join(result)


def clean_markdown(text: str) -> str:
    """Capa 2 (backend) de Fase 3.5 -- garantiza que Telegram/WhatsApp no
    muestren simbolos de Markdown crudos, sin depender de que el LLM siga
    la instruccion del system prompt (Capa 1). Opcion A del documento
    fuente: limpiar a texto plano en vez de traducir a la sintaxis propia
    de cada plataforma.

    flatten_markdown_tables y el stripping de fences corren PRIMERO, antes
    de las sustituciones de asteriscos -- si corrieran despues,
    text.replace("*", "") no afectaria pipes/fences, pero
    _ITALIC_UNDERSCORE_RE si podria comerse guiones bajos dentro de una
    celda de tabla real.
    """
    text = flatten_markdown_tables(text)
    text = _CODE_FENCE_RE.sub(r"\1", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _UNDERSCORE_BOLD_RE.sub(r"\1", text)
    text = _ITALIC_ASTERISK_RE.sub(r"\1", text)
    text = _ITALIC_UNDERSCORE_RE.sub(r"\1", text)
    text = _HEADER_RE.sub("", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    # Cualquier asterisco suelto que no formaba un par valido arriba.
    text = text.replace("*", "")
    return text
