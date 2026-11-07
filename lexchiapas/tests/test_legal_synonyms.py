"""Reglas de expansion de sinonimos legales (app.rag.legal_synonyms)."""

import pytest

from app.rag.legal_synonyms import expand_legal_synonyms


@pytest.mark.parametrize(
    "question,expected_term",
    [
        ("quien hereda si mi papa muere sin testamento", "sucesion legitima"),
        ("mi vecino tumbo un arbol sin permiso", "tala de arboles"),
        ("hay una tala ilegal en el bosque", "tala de arboles"),
        ("me multaron por pasarme un alto", "infracciones de transito"),
        ("me infraccionaron por pasarme el semaforo en rojo", "infracciones de transito"),
        ("mi hijo tiene discapacidad, que apoyos le tocan", "personas con discapacidad"),
        ("mi mama usa silla de ruedas", "personas con discapacidad"),
        ("quiero sacar agua de un pozo", "aprovechamiento de aguas"),
        ("me atendieron mal en el hospital", "usuarios de servicios de salud"),
        ("el doctor de la clinica me trato mal", "usuarios de servicios de salud"),
        ("Me multaron por pasarme un ALTO", "infracciones de transito"),
    ],
)
def test_rule_fires_and_appends_term(question, expected_term):
    expanded, changed = expand_legal_synonyms(question)
    assert changed is True
    assert expanded.startswith(question)  # solo agrega al final, no reemplaza
    assert expected_term in expanded


@pytest.mark.parametrize(
    "question",
    [
        "cuanto es el salario minimo este ano",
        "como tramito mi pasaporte mexicano",
        "me da una receta de mole poblano",
        "que dice el articulo 270 del codigo penal",
        "cual es la pena por el delito de robo",
        "el alto mando del ejercito",  # "alto" suelto no es pasarse un alto
        "una persona sana puede donar sangre",
    ],
)
def test_rule_does_not_fire_on_unrelated_questions(question):
    assert expand_legal_synonyms(question) == (question, False)
