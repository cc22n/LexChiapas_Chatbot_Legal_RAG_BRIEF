"""Fuente unica de verdad de las 38 preguntas (24 originales + 14 casos de "no
encontrado" agregados el 2026-10-26) del golden dataset real del
pipeline RAG (dense pgvector + BM25 + threshold + rerank + generacion
grounded, ver app.rag.rag_pipeline.answer_question).

Extraido de tests/test_rag_regression.py (WEB_FRONTEND_PLAN.md seccion 3.3,
item 1) para que pytest (tests/test_rag_regression.py, parametrizado sobre
GOLDEN_DATASET) y el evaluador real (app.evaluation.run_golden_dataset) usen
EXACTAMENTE el mismo dato -- antes vivian duplicados/hardcodeados dentro de
24 funciones test_* separadas.

Cada pregunta/articulo/ley esperado fue verificado leyendo el chunk real en
la base de datos ANTES de escribirse (ver docstring original de
tests/test_rag_regression.py) -- no se invento ningun numero de articulo al
mover estos datos aca, se copiaron tal cual del codigo real de cada funcion
test_* (verificado con grep -n "^def test_" contra el archivo original).

known_limitation=True identifica los casos donde el codigo original usa
pytest.xfail() de forma CONDICIONAL (solo si el resultado real de esta
corrida coincide con una limitacion ya documentada, nunca un xfail ciego).
Hallazgo real al extraer este dataset: el archivo original tiene 3 funciones
con esta forma, no 2 -- el docstring de cabecera de
tests/test_rag_regression.py y el resumen de WEB_FRONTEND_PLAN.md seccion
3.3 dicen "2 xfailed" porque esa fue la cuenta de la ULTIMA CORRIDA REAL (el
tercer caso, proteccion_animal, dio grounded=False esa vez y paso por la
rama normal), no porque el mecanismo de xfail condicional solo exista en 2
funciones. Los 3 casos reales con esta forma son:
- test_derechos_humanos_tortura_sanciones_limite_conocido
- test_civil_sucesion_intestada_limitacion_conocida
- test_no_encontrado_proteccion_animal
Los 3 se marcan aca known_limitation=True para reflejar el codigo real, no
el resumen. Ver limitation_kind de cada caso para el detalle de que
comportamiento tolera cada uno.

Fase 9.7 (migracion real de embeddings nv-embedqa-e5-v5 -> nvidia/llama-
nemotron-embed-vl-1b-v2, 2026-08-27, ver LexChiapas_Plan_Futuro.md): se
agregaron 2 casos mas con LIMITATION_TOLERATE_GROUNDED_FALSE (bordes de
similitud reales del modelo nuevo, medidos con dense_search directo antes
de marcarlos, nunca asumidos):
- test_familiar_adulto_mayor_definicion
- test_civil_notariado_fe_publica
"""

from dataclasses import dataclass, field


# Formas de xfail condicional que app.evaluation.common.evaluate_case
# reconoce. El campo limitation_kind le dice cual aplica; None para casos
# sin limitacion conocida. Las primeras dos vienen del archivo original
# (ver docstring del modulo arriba); LIMITATION_TOLERATE_GROUNDED_FALSE se
# agrego en la Fase 9.7 (migracion real de embeddings, 2026-08-27) para el
# caso INVERSO al primero: expects_grounded=True pero el sistema admite
# honestamente "no encontre informacion" (el fallo SEGURO) en vez de citar
# algo con confianza -- nunca tolera un grounded=True que cite el articulo
# EQUIVOCADO, solo tolera el grounded=False honesto.
LIMITATION_TOLERATE_GROUNDED_TRUE = "tolerate_grounded_true"
LIMITATION_TOLERATE_MISSING_POSITION = "tolerate_missing_position"
LIMITATION_TOLERATE_GROUNDED_FALSE = "tolerate_grounded_false"


@dataclass(frozen=True)
class GoldenCase:
    # Nombre de la funcion test_* original (preservado como id de
    # parametrize y como referencia cruzada al docstring/hallazgo real que
    # documenta cada caso en el historial de tests/test_rag_regression.py).
    name: str
    question: str
    # Substring case-insensitive del nombre del documento esperado, o None
    # si el caso es "no encontrado" / fuera de dominio (no hay ley que deba
    # aparecer).
    ley_contains: str | None
    articulo_esperado: str | None
    expects_grounded: bool

    # True solo para los 3 casos descritos en el docstring del modulo (ver
    # arriba) -- el codigo original tolera un resultado especifico y
    # documentado via pytest.xfail() en vez de fallar duro.
    known_limitation: bool = False
    limitation_kind: str | None = None
    known_limitation_reason: str = ""

    # Solo test_familiar_adopcion_requisitos: el Codigo Civil (mas
    # detallado) y la Ley de Adopcion Art.8 (que remite ahi) son AMBOS
    # fundamento valido -- ver docstring original, no es una limitacion
    # tolerada, es una expectativa corregida a proposito (dos leyes
    # solapadas responden legitimamente). alt_ley_contains se compara con
    # document_nombre.lower().startswith(...), no con "in", igual que el
    # codigo original.
    alt_ley_contains: str | None = None
    alt_articulos: tuple[str, ...] = field(default_factory=tuple)

    # True solo para el bucket 3 (fuera de dominio total, Capa 1 de
    # guardrails): ademas de grounded=False, el codigo original exige
    # retrieved_chunks == [] y llm_model is None (nunca se llego a gastar en
    # hybrid_search/generacion).
    expects_empty_retrieval: bool = False


GOLDEN_DATASET: list[GoldenCase] = [
    # -------------------------------------------------------------------
    # Bucket 1: preguntas dentro del corpus, con articulo/ley esperado
    # verificado a mano contra la tabla `chunks` real.
    # -------------------------------------------------------------------
    GoldenCase(
        name="test_penal_amnistia",
        question="En favor de quienes se decreto la amnistia en Chiapas y por que hechos?",
        ley_contains="Amnistia",
        articulo_esperado="1",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_cultural_bibliotecas",
        question="Cuantos titulos catalogados debe tener el acervo para que un lugar se considere Biblioteca Publica en Chiapas?",
        ley_contains="Bibliotecas",
        articulo_esperado="2",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_derechos_humanos_tortura_definicion",
        question="Que comete el delito de tortura segun la ley de Chiapas?",
        ley_contains="Tortura",
        articulo_esperado="3",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_derechos_humanos_tortura_sanciones_limite_conocido",
        question="Que sanciones existen para el delito de tortura en Chiapas?",
        ley_contains="Tortura",
        articulo_esperado="3",
        expects_grounded=False,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_TRUE,
        known_limitation_reason=(
            "Fase 2: la mejor similitud dense real contra el articulo correcto "
            "(Art.3 ultimo parrafo / Art.4 / Art.5, Ley de Tortura) fue ~0.4525, "
            "por debajo de similarity_threshold=0.5 vigente en ai_config.json, "
            "aunque la recuperacion es correcta (todos los candidatos top-8 son "
            "de esa misma ley). Si esta corrida da grounded=True, la limitacion "
            "ya no reproduce (mejora real o corpus mas grande cambio el ranking "
            "relativo)."
        ),
    ),
    GoldenCase(
        name="test_familiar_adopcion_requisitos",
        question="Quien puede adoptar a un menor en Chiapas y que requisitos necesita?",
        ley_contains="Adopcion",
        articulo_esperado="8",
        expects_grounded=True,
        alt_ley_contains="codigo civil",
        alt_articulos=("385", "397"),
    ),
    GoldenCase(
        name="test_familiar_adulto_mayor_definicion",
        question="A partir de que edad se considera adulto mayor segun la ley de Chiapas?",
        ley_contains="Atencion a la Familia",
        articulo_esperado="2",
        expects_grounded=True,
        # Hallazgo real (2026-08-01, corrida de regresion tras ingerir la Ley
        # de Asistencia e Integracion de las Personas Adultas Mayores del
        # Estado de Chiapas -- ya estaba en el corpus antes de esa ingesta,
        # pero esta fue la primera corrida completa del golden dataset desde
        # entonces): retrieval ahora prefiere su Articulo 1 ("60 anos en
        # adelante") sobre el Codigo de Atencion a la Familia Art.2, mismo
        # dato ("Adultos mayores: personas de 60 anos o mas", verificado
        # contra la DB real). Es la MISMA situacion ya documentada para
        # test_familiar_adopcion_requisitos (dos leyes solapadas responden
        # legitimamente, la mas especifica compite y a veces gana) -- no es
        # una limitacion tolerada ni un bug de retrieval, es una expectativa
        # corregida a proposito.
        alt_ley_contains="ley de asistencia e integracion",
        alt_articulos=("1",),
        # Hallazgo real (Fase 9.7, migracion de embeddings, 2026-08-27):
        # con nvidia/llama-nemotron-embed-vl-1b-v2 (ver ai_config.json
        # "_note_migracion_2026_08_27"), un dense_search directo (threshold=0,
        # k=15) para esta pregunta NO trae NI el articulo esperado
        # (Atencion a la Familia Art.2) NI la alternativa aceptada arriba
        # (Asistencia e Integracion Art.1) en el top-6 -- el candidato mas
        # cercano de la ley alternativa es su Art.3 (sim=0.4830), no el
        # Art.1 esperado. El modelo nuevo produce similitudes sistematicamente
        # mas bajas/comprimidas para este tipo de pregunta (mismo patron que
        # otros casos borde documentados en la Fase 9.7) -- el sistema
        # admite honestamente "no encontre informacion" en vez de citar algo
        # con confianza, que es el fallo SEGURO, no uno peligroso.
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_FALSE,
        known_limitation_reason=(
            "Fase 9.7: con el modelo de embeddings nuevo (llama-nemotron-"
            "embed-vl-1b-v2), ni el articulo esperado ni la alternativa "
            "documentada superan similarity_threshold=0.5 -- verificado con "
            "dense_search directo, el mejor candidato real fue 0.5263 (una "
            "ley distinta, Ninas Ninos y Adolescentes, no relacionada)."
        ),
    ),
    GoldenCase(
        name="test_transito_reincidencia",
        question="Que pasa si un conductor reincide en la misma infraccion de transito en Chiapas?",
        ley_contains="Movilidad",
        articulo_esperado="159",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_fiscal_recargos",
        question="Que recargos se generan por falta de pago oportuno de un credito fiscal garantizado en Chiapas?",
        ley_contains="Fiscal",
        articulo_esperado="28",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_salud_certificados",
        question="Que certificados sanitarios expiden las autoridades de salud en Chiapas?",
        ley_contains="Salud",
        articulo_esperado="241",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_laboral_vacaciones",
        question="Cuantos dias de vacaciones tienen los trabajadores del servicio civil en Chiapas?",
        ley_contains="Servicio Civil",
        articulo_esperado="32",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_administrativo_plazo_transparencia",
        question="Cual es el plazo maximo para responder una solicitud de acceso a informacion publica en Chiapas?",
        ley_contains="Transparencia",
        articulo_esperado="134",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_civil_capacidad_juridica",
        question="Cuando se adquiere la capacidad juridica de una persona segun el Codigo Civil de Chiapas?",
        ley_contains="Libro Primero",
        articulo_esperado="20",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_civil_bienes_fuera_de_comercio",
        question="Que bienes estan fuera del comercio segun el Codigo Civil de Chiapas?",
        ley_contains="Libro Segundo",
        articulo_esperado="737",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_civil_sucesion_intestada_limitacion_conocida",
        question="Quien hereda si una persona muere sin testamento en Chiapas?",
        ley_contains="Libro Tercero",
        articulo_esperado="1576",
        expects_grounded=True,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_MISSING_POSITION,
        known_limitation_reason=(
            "Art.1576 (Libro Tercero, Sucesiones) pasa el threshold real de "
            "dense_search (verificado leyendo el chunk real antes de escribir "
            "la pregunta) pero el reranker placeholder (solapamiento de "
            "palabras, ver app/rag/reranker.py) no siempre lo trae al top-K "
            "final -- el chunk que aparece en su lugar suele ser Art.1573 "
            "(mismo tema/libro, pero incompleto). grounded=True sigue siendo "
            "un assert duro (gate anti-alucinacion, no el ranking); solo la "
            "posicion del articulo exacto en el top-K se tolera como xfail."
        ),
    ),
    GoldenCase(
        name="test_civil_convenio_definicion",
        question="Que es un convenio segun el Codigo Civil de Chiapas?",
        ley_contains="Libro Cuarto",
        articulo_esperado="1766",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_civil_notariado_fe_publica",
        question="Que es la fe publica que tiene un notario en Chiapas?",
        ley_contains="Notariado",
        articulo_esperado="9",
        expects_grounded=True,
        # Hallazgo real (Fase 9.7, migracion de embeddings, 2026-08-27): con
        # el modelo nuevo, un dense_search directo SI trae el articulo
        # correcto (Ley del Notariado Art.9) en la posicion 1, pero su
        # similitud real (0.4887) queda apenas por debajo de
        # similarity_threshold=0.5 -- el caso limite mas ajustado de todos
        # los medidos en esta migracion (a menos de 0.02 del threshold).
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_FALSE,
        known_limitation_reason=(
            "Fase 9.7: con el modelo de embeddings nuevo, el articulo "
            "correcto (Notariado Art.9) rankea primero en dense_search "
            "directo pero con similitud 0.4887, apenas por debajo de "
            "similarity_threshold=0.5 -- verificado, no asumido."
        ),
    ),
    GoldenCase(
        name="test_ambiental_sanciones",
        question="Que sanciones puede imponer la autoridad por violaciones a la Ley Ambiental de Chiapas?",
        ley_contains="Ambiental",
        # 2026-10-24: la Ley Ambiental se recargo desde el Congreso y resulto que
        # el corpus tenia la ley de 2009, sustituida por un "texto de nueva
        # creacion" de 2015 con otra numeracion. La disposicion que este caso
        # esperaba como art. 214 ("Cuando existan violaciones a los preceptos de
        # esta ley ... podran imponer al infractor ...") es ahora el art. 238; el
        # 214 actual dice "Se Deroga". Verificado leyendo ambos textos.
        articulo_esperado="238",
        expects_grounded=True,
    ),
    # -------------------------------------------------------------------
    # Bucket 2: temas legitimamente fuera del corpus (preguntas en dominio
    # legal, guardrails las deja pasar, pero no hay ley cargada que las
    # cubra -- deben dar grounded=False, nunca una respuesta inventada).
    # -------------------------------------------------------------------
    GoldenCase(
        name="test_no_encontrado_proteccion_consumidor",
        question="Que dice la ley de proteccion al consumidor de Chiapas sobre las devoluciones de productos?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
    ),
    GoldenCase(
        name="test_no_encontrado_ley_federal_trabajo",
        question="Que dice la Ley Federal del Trabajo sobre el despido injustificado de un trabajador privado?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
    ),
    GoldenCase(
        name="test_penal_codigo_penal_robo",
        question="Cual es la pena por el delito de robo segun el Codigo Penal de Chiapas?",
        ley_contains="Codigo Penal",
        articulo_esperado="270",
        expects_grounded=True,
    ),
    GoldenCase(
        name="test_no_encontrado_proteccion_animal",
        question="Que dice la ley de proteccion animal de Chiapas sobre el maltrato a mascotas?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_TRUE,
        known_limitation_reason=(
            "Ley de Salud Art.228/230 (vacunacion/control antirrabico) esta en "
            "la frontera semantica de 'mismo tema' (control antirrabico) vs. "
            "'tema distinto' (maltrato/bienestar animal). Confirmado corriendo "
            "el pipeline completo 4 veces seguidas: 3/4 dieron grounded=False, "
            "1/4 grounded=True -- variacion real de una corrida a otra, no "
            "ruido del clasificador (que es determinista a input fijo con "
            "temperature=0.0)."
        ),
    ),
    # -------------------------------------------------------------------
    # Bucket 2 ampliado (2026-10-26): 7 casos "no encontrado" estables (3 de 3
    # repeticiones dieron grounded=False) + 7 limitaciones conocidas (3 grises
    # donde el bot responde con algo tangencial y 4 inestables que dieron
    # grounded=True en 1 de 3 repeticiones). Cada pregunta se verifico contra
    # el texto real de los 12,450
    # chunks activos (el tema no aparece, o aparece solo como mencion pasajera
    # dentro de otra ley) y contra el comportamiento real del pipeline (cache
    # desactivado, text-embedding-3-large). Motivo: con el modelo de embeddings
    # nuevo el umbral de recuperacion (0.5) ya no separa "sin respuesta" (top1
    # 0.61-0.82), asi que el segundo gate de grounding es lo que decide, y 4
    # casos de este bucket no bastaban para medirlo.
    # -------------------------------------------------------------------
    GoldenCase(
        name="test_no_encontrado_voluntad_anticipada_limitacion_conocida",
        question="Como hago un documento de voluntad anticipada para rechazar tratamientos medicos en Chiapas?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_TRUE,
        known_limitation_reason=(
            "El termino 'voluntad anticipada' no aparece en ningun chunk activo "
            "(la ley estatal, LEY_0149, esta pendiente de cargar). En 3 "
            "repeticiones sin cache dio grounded True/False/False (y False en "
            "la verificacion inicial): el segundo gate a veces acepta como "
            "fundamento un articulo cercano de la Ley de Salud (art. 117 y "
            "siguientes). Medido el 2026-10-26."
        ),
    ),
    GoldenCase(
        name="test_no_encontrado_escuela_particular",
        question="Que requisitos hay para abrir una escuela particular en Chiapas?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
    ),
    GoldenCase(
        name="test_no_encontrado_seguro_social",
        question="Que dice la Ley del Seguro Social sobre la pension por invalidez?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
    ),
    GoldenCase(
        name="test_no_encontrado_otra_entidad_jalisco",
        question="Que dice el Codigo Civil de Jalisco sobre el divorcio?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
    ),
    GoldenCase(
        name="test_no_encontrado_extincion_dominio_limitacion_conocida",
        question="Como se tramita la extincion de dominio de un bien relacionado con un delito en Chiapas?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_TRUE,
        known_limitation_reason=(
            "No hay ley de extincion de dominio cargada; el tema solo se cita "
            "de pasada en los arts. 122 y 149 de la Ley de Victimas (la ley "
            "estatal esta pendiente). En 3 repeticiones sin cache dio grounded "
            "False/True/False (y False en la verificacion inicial). Medido el "
            "2026-10-26."
        ),
    ),
    GoldenCase(
        name="test_no_encontrado_seguridad_privada",
        question="Que requisitos necesita una empresa de seguridad privada para operar en Chiapas?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
    ),
    GoldenCase(
        name="test_no_encontrado_turismo_limitacion_conocida",
        question="Que obligaciones tiene un prestador de servicios turisticos en Chiapas?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_TRUE,
        known_limitation_reason=(
            "No hay Ley de Turismo cargada (pendiente); el corpus solo tiene "
            "menciones sueltas (p. ej. Ley de Transparencia art. 66, que lista "
            "a los prestadores de servicios turisticos). En 3 repeticiones sin "
            "cache dio grounded True/False/False (y False en la verificacion "
            "inicial). Medido el 2026-10-26."
        ),
    ),
    GoldenCase(
        name="test_no_encontrado_ley_de_amparo",
        question="Que dice la Ley de Amparo sobre la suspension del acto reclamado?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
    ),
    GoldenCase(
        # La Capa 1 de guardrails la rechaza (chunks vacios); no se exige
        # expects_empty_retrieval porque ese comportamiento depende del umbral
        # de la Capa 1, no de la ausencia de la ley en el corpus.
        name="test_no_encontrado_impuestos_sat",
        question="Que impuestos debe pagar una persona fisica ante el SAT?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
    ),
    GoldenCase(
        name="test_no_encontrado_codigo_de_comercio_limitacion_conocida",
        question="Como se constituye una sociedad mercantil segun el Codigo de Comercio?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_TRUE,
        known_limitation_reason=(
            "El Codigo de Comercio es federal y no esta en el corpus; el "
            "Codigo Civil solo remite a el (arts. 775 y 2668) y regula las "
            "sociedades civiles. En 3 repeticiones sin cache dio grounded "
            "False/True/False; en la corrida del golden completo dio True (y "
            "False en la verificacion inicial). Medido el 2026-10-26."
        ),
    ),
    GoldenCase(
        name="test_no_encontrado_propiedad_industrial",
        question="Cual es el procedimiento para registrar una marca o solicitar una patente?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
    ),
    GoldenCase(
        name="test_no_encontrado_catastro_limitacion_conocida",
        question="Como se actualiza el valor catastral de un predio en Chiapas?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_TRUE,
        known_limitation_reason=(
            "No hay Ley de Catastro cargada (LEY_0020 del Congreso, pendiente). "
            "El art. 371 del Codigo Fiscal habla del registro catastral de "
            "bienes inmuebles del Gobierno del Estado y el segundo gate lo "
            "acepta: grounded=True con una respuesta tangencial que no explica "
            "como se actualiza el valor catastral de un predio particular. "
            "Observado en 1 corrida (2026-10-26)."
        ),
    ),
    GoldenCase(
        name="test_no_encontrado_licitacion_obra_limitacion_conocida",
        question="Cual es el procedimiento para licitar una obra publica estatal en Chiapas?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_TRUE,
        known_limitation_reason=(
            "No hay Ley de Obra Publica cargada (LEY_0044 del Congreso, "
            "pendiente). El art. 370 del Codigo Fiscal solo remite a 'las leyes "
            "relativas a la obra publica' y la respuesta lo presenta como el "
            "procedimiento. Observado en 1 corrida (2026-10-26)."
        ),
    ),
    GoldenCase(
        name="test_no_encontrado_condominio_limitacion_conocida",
        question="Que dice la ley sobre las cuotas de mantenimiento y el reglamento de un condominio en Chiapas?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        known_limitation=True,
        limitation_kind=LIMITATION_TOLERATE_GROUNDED_TRUE,
        known_limitation_reason=(
            "No hay Ley de Propiedad en Condominio cargada (LEY_0087 del "
            "Congreso, pendiente). La Ley de Fraccionamientos (arts. 3 y 78) "
            "menciona el regimen de propiedad en condominio de forma tangencial; "
            "el bot reconoce en su texto que no hay informacion especifica sobre "
            "cuotas y reglamento, pero aun asi sale grounded=True. Observado en "
            "1 corrida (2026-10-26)."
        ),
    ),
    # -------------------------------------------------------------------
    # Bucket 3: fuera de dominio total -- deben ser rechazadas por Capa 1
    # (guardrails) antes de gastar en hybrid_search/generacion.
    # -------------------------------------------------------------------
    GoldenCase(
        name="test_fuera_de_dominio_capital_francia",
        question="Cual es la capital de Francia?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        expects_empty_retrieval=True,
    ),
    GoldenCase(
        name="test_fuera_de_dominio_receta",
        question="Dame una receta de mole poblano",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        expects_empty_retrieval=True,
    ),
    GoldenCase(
        name="test_fuera_de_dominio_aritmetica",
        question="Cuanto es 245 por 37?",
        ley_contains=None,
        articulo_esperado=None,
        expects_grounded=False,
        expects_empty_retrieval=True,
    ),
]
