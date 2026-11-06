"""Detector de frases de relleno (app.rag.filler_guard). Los textos son las
respuestas reales de 'como se constituye una sociedad anonima' (sin acentos:
el modulo normaliza y los .py del proyecto van en ASCII)."""

from app.rag.filler_guard import strip_unsupported_filler

SOCIEDAD_ANONIMA = (
    "Los fragmentos legales proporcionados no contienen informacion especifica sobre la "
    "constitucion de una sociedad anonima en Chiapas. Sin embargo, el Codigo Civil para el "
    "Estado de Chiapas menciona en el Articulo 2666 que el contrato de sociedad debe incluir "
    "los nombres de los otorgantes, la razon social y el importe del capital social.\n\n"
    "Para constituir una sociedad anonima, generalmente se requiere seguir un proceso que "
    "incluye la elaboracion de un acta constitutiva. Te recomendaria consultar con un abogado "
    "o un notario para obtener informacion detallada.\n\n"
    "Este mensaje es informativo y no sustituye la asesoria de un abogado."
)


def test_sociedad_anonima_filler_is_removed_and_flagged():
    cleaned, flagged = strip_unsupported_filler(SOCIEDAD_ANONIMA)
    assert flagged is True
    assert "generalmente" not in cleaned
    assert "acta constitutiva" not in cleaned
    # Lo respaldado por el fragmento y el cierre se conservan.
    assert "Articulo 2666" in cleaned
    assert "no sustituye la asesoria" in cleaned
    assert "Te recomendaria consultar con un abogado" in cleaned
    # Los parrafos siguen separados.
    assert "\n\n" in cleaned


def test_honest_admission_without_filler_is_untouched():
    answer = (
        "No hay informacion especifica sobre cuotas de condominio en los fragmentos. "
        "El Articulo 3 de la Ley de Fraccionamientos menciona el regimen de condominio."
    )
    assert strip_unsupported_filler(answer) == (answer, False)


def test_grounded_answer_with_generalmente_but_no_admission_is_untouched():
    answer = "Segun el Articulo 12, el plazo generalmente es de cinco dias habiles."
    assert strip_unsupported_filler(answer) == (answer, False)


def test_accented_text_is_detected_too():
    answer = "No tengo información específica sobre eso. Normalmente se hace así. Fin."
    cleaned, flagged = strip_unsupported_filler(answer)
    assert flagged is True
    assert "Normalmente" not in cleaned
    assert cleaned.startswith("No tengo información específica")


def test_all_sentences_filler_keeps_original_text_but_still_flags():
    answer = "No hay informacion en los fragmentos. Generalmente depende del caso."
    cleaned, flagged = strip_unsupported_filler(answer)
    assert flagged is True
    assert cleaned == "No hay informacion en los fragmentos."


def test_only_filler_sentence_left_returns_original():
    answer = "No hay informacion sobre eso, normalmente se tramita ante el notario."
    cleaned, flagged = strip_unsupported_filler(answer)
    assert flagged is True
    assert cleaned == answer


def test_empty_answer():
    assert strip_unsupported_filler("") == ("", False)
