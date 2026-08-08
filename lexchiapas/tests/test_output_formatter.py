from app.bots.output_formatter import clean_markdown, flatten_markdown_tables

TABLE_TEXT = """Aqui hay una comparacion de sanciones.

| Ley, Articulo | Sancion | Autoridad |
|---|---|---|
| Ley de Salud, Art. 45 | multa de 50 UMA | Secretaria de Salud |
| Ley Ambiental, Art. 12 | No especificado | No especificado |

Eso es todo."""


def test_flatten_markdown_tables_converts_rows_to_readable_paragraphs():
    result = flatten_markdown_tables(TABLE_TEXT)

    assert "|" not in result
    assert "Ley de Salud, Art. 45: Sancion: multa de 50 UMA; Autoridad: Secretaria de Salud" in result
    assert "Ley Ambiental, Art. 12: Sancion: No especificado; Autoridad: No especificado" in result
    # El texto alrededor de la tabla no se toca.
    assert "Aqui hay una comparacion de sanciones." in result
    assert "Eso es todo." in result


def test_flatten_markdown_tables_ignores_prose_with_pipes():
    # Sin linea separadora real (|---|---|), no es una tabla -- texto que
    # casualmente use "|" no debe tocarse.
    text = "El limite es de 5 | 10 UMA segun el caso."
    assert flatten_markdown_tables(text) == text


def test_flatten_markdown_tables_handles_text_without_any_table():
    text = "Una respuesta normal sin ninguna tabla, solo texto plano."
    assert flatten_markdown_tables(text) == text


def test_clean_markdown_flattens_tables_before_stripping_asterisks():
    # BUG REAL evitado (Fase 9, contenido visual): si el orden fuera al
    # reves, text.replace("*", "") no rompe nada de la tabla, pero
    # verificamos igual que el pipeline completo (clean_markdown, el que de
    # verdad usa telegram_bot.py) deja el resultado limpio y legible.
    result = clean_markdown(TABLE_TEXT)
    assert "|" not in result
    assert "Ley de Salud, Art. 45: Sancion: multa de 50 UMA; Autoridad: Secretaria de Salud" in result


def test_clean_markdown_strips_code_fences_as_defense_in_depth():
    # El LLM tiene prohibido mandar fences (ver generator._FORMATO_CON_TABLAS),
    # pero si uno se cuela igual, no debe llegar crudo a Telegram.
    text = "Antes.\n```mermaid\ngraph TD; A-->B;\n```\nDespues."
    result = clean_markdown(text)
    assert "```" not in result
    assert "Antes." in result
    assert "Despues." in result
