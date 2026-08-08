from app.rag import generator


def test_system_prompt_defaults_to_plain_text_without_the_flag(monkeypatch):
    monkeypatch.setattr(generator, "get_ai_config", lambda: {})
    prompt = generator._system_prompt()
    assert "REGLAS DE FORMATO: responde en texto plano. No uses asteriscos" in prompt
    assert "tabla" not in prompt.lower()


def test_system_prompt_allows_tables_when_flag_enabled(monkeypatch):
    monkeypatch.setattr(
        generator,
        "get_ai_config",
        lambda: {"visual_answers": {"comparison_tables": {"enabled": True}}},
    )
    prompt = generator._system_prompt()
    assert "tabla" in prompt.lower()
    # La prohibicion de bold/italic/headers/listas sigue presente -- la
    # bandera solo abre UNA excepcion nominal, no relaja el formato en general.
    assert "asteriscos" in prompt
    assert "No especificado" in prompt  # regla anti-alucinacion de celda


def test_system_prompt_flag_disabled_explicitly(monkeypatch):
    monkeypatch.setattr(
        generator,
        "get_ai_config",
        lambda: {"visual_answers": {"comparison_tables": {"enabled": False}}},
    )
    prompt = generator._system_prompt()
    assert "tabla" not in prompt.lower()


def test_system_prompt_constant_matches_default_behavior():
    # SYSTEM_PROMPT (el simbolo publico del modulo) debe coincidir con lo
    # que produce _system_prompt() sin ninguna bandera -- base + formato
    # texto plano + estilo cotidiano (default de las dos, switch tecnico/
    # cotidiano agregado 2026-08-10). ai_config.json real puede tener
    # comparison_tables activo, asi que se mockea para aislar la comparacion
    # de la config en vivo (mismo patron que el resto de este archivo).
    assert generator.SYSTEM_PROMPT == (
        generator._PROMPT_BASE + generator._FORMATO_TEXTO_PLANO + generator._ESTILO_COTIDIANO
    )


def test_system_prompt_matches_no_flags_state(monkeypatch):
    monkeypatch.setattr(generator, "get_ai_config", lambda: {})
    assert generator.SYSTEM_PROMPT == generator._system_prompt()
    assert generator.SYSTEM_PROMPT == generator._system_prompt(technical=False)


def test_system_prompt_technical_switch_changes_register_not_content_rules(monkeypatch):
    monkeypatch.setattr(generator, "get_ai_config", lambda: {})
    cotidiano = generator._system_prompt(technical=False)
    tecnico = generator._system_prompt(technical=True)

    assert cotidiano != tecnico
    # Ambos registros heredan _PROMPT_BASE completo -- el switch nunca debe
    # relajar la obligacion de citar ley+articulo ni el gate de grounding.
    assert generator._PROMPT_BASE in cotidiano
    assert generator._PROMPT_BASE in tecnico
    assert "lenguaje simple" in cotidiano
    assert "lenguaje juridico formal" in tecnico


def test_build_prompt_uses_system_prompt_selection(monkeypatch):
    monkeypatch.setattr(
        generator,
        "get_ai_config",
        lambda: {"visual_answers": {"comparison_tables": {"enabled": True}}},
    )
    messages = generator.build_prompt("Compara dos leyes", [])
    assert messages[0]["role"] == "system"
    assert "tabla" in messages[0]["content"].lower()
