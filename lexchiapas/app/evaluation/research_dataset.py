"""Preguntas que cruzan varias leyes, para comparar la ruta normal contra el modo
investigacion (LexChiapas_Plan_Agente_Investigacion.md, 10.4).

Cada caso lista GRUPOS de leyes: la respuesta "cubre" un grupo si alguno de los
fragmentos recuperados pertenece a una ley cuyo nombre contiene alguna de las
subcadenas del grupo (sin acentos, sin distinguir mayusculas). La metrica es la
fraccion de grupos cubiertos; no juzga la calidad de la respuesta, solo si la
busqueda llego a las leyes que la pregunta pide cruzar.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchCase:
    name: str
    question: str
    # Cada grupo es una tupla de subcadenas alternativas del nombre de la ley.
    law_groups: tuple[tuple[str, ...], ...]


RESEARCH_CASES: list[ResearchCase] = [
    ResearchCase(
        name="despido_ayuntamiento",
        question="Me despidieron del ayuntamiento sin pagarme, que puedo hacer y que ley me protege?",
        law_groups=(("Servicio Civil",),),
    ),
    ResearchCase(
        name="construir_terreno_agricola_rio",
        question="Quiero construir una casa en un terreno agricola junto a un rio, que permisos necesito y que pasa si contamino el agua?",
        law_groups=(("Asentamientos Humanos",), ("Aguas", "Ambiental")),
    ),
    ResearchCase(
        name="funcionario_pide_dinero",
        question="Si un funcionario me pide dinero para hacer un tramite, que delito comete y que responsabilidad administrativa tiene?",
        law_groups=(("Codigo Penal",), ("Responsabilidades Administrativas",)),
    ),
    ResearchCase(
        name="seguridad_privada_impuestos",
        question="Para abrir una empresa de seguridad privada, que requisitos necesito y que impuestos estatales debo pagar?",
        law_groups=(("Seguridad Privada",), ("Fiscal",)),
    ),
    ResearchCase(
        name="herencia_condominio",
        question="Mi papa murio sin testamento y dejo un departamento en condominio, quien hereda y quien paga las cuotas de mantenimiento?",
        law_groups=(("Libro Tercero",), ("Condominio",)),
    ),
    ResearchCase(
        name="discapacidad_discriminacion_escuela",
        question="Una persona con discapacidad sufre discriminacion en una escuela, que leyes la protegen y que puede hacer?",
        law_groups=(("Discapacidad",), ("Discriminacion",), ("Educacion",)),
    ),
    ResearchCase(
        name="obra_publica_responsabilidad",
        question="Un servidor publico adjudico una obra publica sin licitacion, que dice la ley de obra publica y que responsabilidad tiene?",
        law_groups=(("Obra Publica",), ("Responsabilidades Administrativas", "Codigo Penal")),
    ),
]
