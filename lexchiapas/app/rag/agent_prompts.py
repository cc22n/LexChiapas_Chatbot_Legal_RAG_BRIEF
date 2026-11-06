"""Prompts del agente (nodos decidir y reformular). Solo constantes: el texto no
cambia al moverlo desde agent_pipeline.py; el uso esta en los nodos."""

# Migrado a JSON mode (2026-08-06, auditoria de integracion LLM -- ver
# LexChiapas_Plan_Futuro.md Parte C.1 para el experimento real que confirmo
# response_format={"type":"json_object"} viable en 4/5 proveedores del
# fallback_order: minimax-m3, glm-5.2, gpt-4o-mini, grok-4.20 aceptaron el
# parametro y devolvieron JSON valido de forma confiable; deepseek-v4-pro
# dio timeout en el experimento, INCONCLUSO por infra, no por
# incompatibilidad real -- si falla con este parametro, generate_with_fallback
# ya lo trata como cualquier otro fallo de proveedor y pasa al siguiente). El
# parser de texto plano (_parse_decision) se mantiene intacto como red de
# seguridad para el proveedor que ignore response_format -- ver
# _parse_decision_json/_parse_decision abajo.
DECIDE_SYSTEM_PROMPT = (
    "Analizas una pregunta de un usuario sobre leyes y reglamentos de "
    "Chiapas, Mexico, para decidir COMO buscar la respuesta. Responde "
    "UNICAMENTE con un objeto JSON, sin texto adicional antes ni despues, "
    "con EXACTAMENTE estas 3 claves:\n"
    '{"accion": "<NINGUNA|BUSQUEDA_GENERAL|BUSQUEDA_POR_LEY|ARTICULO_ESPECIFICO|HISTORIAL_LEY>", '
    '"ley": <nombre de la ley o codigo mencionado explicitamente, o null>, '
    '"articulo": <numero de articulo mencionado explicitamente, o null>}\n\n'
    "Para 'ley': si el usuario escribio un nombre COMPLETO u oficial (incluye "
    "frases como 'de Procedimientos', 'para el Estado de Chiapas', numero de "
    "Libro, etc.), copialo TAL CUAL lo escribio, sin acortarlo -- varias leyes "
    "de Chiapas comparten las mismas palabras clave (ej. 'Codigo Penal' vs "
    "'Codigo de Procedimientos Penales'; los distintos Libros del 'Codigo "
    "Civil') y acortar el nombre le impide al sistema distinguir cual de "
    "ellas es. Usa una forma corta/generica (ej. 'codigo penal') SOLO cuando "
    "el usuario mismo la uso de forma corta.\n\n"
    "Usa ARTICULO_ESPECIFICO SOLO si la pregunta pide el contenido VIGENTE de "
    "un numero de articulo concreto de una ley identificable (ej. 'que dice "
    "el articulo 45 del codigo civil de Chiapas'). Usa HISTORIAL_LEY si la "
    "pregunta es sobre la HISTORIA de una ley o articulo -- sus reformas, "
    "derogaciones, adiciones, o que le paso a traves del tiempo (ej. 'que "
    "reformas ha tenido el codigo civil de Chiapas', 'que le paso a la ley "
    "de proteccion animal', 'cuando se reformo el articulo 214 del codigo "
    "penal') -- en vez de su contenido vigente actual; requiere identificar "
    "la ley igual que BUSQUEDA_POR_LEY. Usa BUSQUEDA_POR_LEY si la pregunta "
    "menciona una ley o codigo especifico por nombre pero NO pide un numero "
    "de articulo puntual ni su historial de reformas. Usa BUSQUEDA_GENERAL "
    "para cualquier otra pregunta legal de Chiapas sin ley especifica "
    "mencionada. Usa NINGUNA solo si la pregunta claramente no requiere "
    "ninguna busqueda legal (saludo, agradecimiento, despedida).\n\n"
    "Ejemplo 1:\n"
    "Pregunta: Que sanciones existen por tortura en Chiapas?\n"
    '{"accion": "BUSQUEDA_GENERAL", "ley": null, "articulo": null}\n\n'
    "Ejemplo 2:\n"
    "Pregunta: Que dice el articulo 270 del codigo penal de Chiapas?\n"
    '{"accion": "ARTICULO_ESPECIFICO", "ley": "codigo penal", "articulo": "270"}\n\n'
    "Ejemplo 3:\n"
    "Pregunta: Que dice la ley de transparencia de Chiapas sobre solicitudes de informacion?\n"
    '{"accion": "BUSQUEDA_POR_LEY", "ley": "ley de transparencia", "articulo": null}\n\n'
    "Ejemplo 4:\n"
    "Pregunta: Gracias, eso era todo\n"
    '{"accion": "NINGUNA", "ley": null, "articulo": null}\n\n'
    "Ejemplo 5:\n"
    "Pregunta: Que reformas ha tenido el Codigo de Atencion a la Familia de Chiapas?\n"
    '{"accion": "HISTORIAL_LEY", "ley": "codigo de atencion a la familia", "articulo": null}\n\n'
    "Ejemplo 6 (nombre completo -- NO acortar, ver instruccion arriba):\n"
    "Pregunta: Que dice el articulo 270 del Codigo Penal para el Estado de Chiapas?\n"
    '{"accion": "ARTICULO_ESPECIFICO", "ley": "Codigo Penal para el Estado de Chiapas", "articulo": "270"}'
)


REFORMULATE_SYSTEM_PROMPT = (
    "Ayudas a mejorar una busqueda de textos legales de Chiapas, Mexico. Un "
    "primer intento de busqueda con la consulta de abajo NO encontro "
    "pasajes que respondieran bien la pregunta del usuario. Reformula la "
    "consulta de busqueda como una version ALTERNATIVA, breve, en espanol, "
    "usando terminologia legal distinta a la original -- sinonimos "
    "juridicos, el nombre tecnico de la institucion legal en vez de "
    "lenguaje coloquial, o una formulacion mas general o mas especifica "
    "segun convenga. NO inventes el nombre de una ley, codigo o articulo "
    "que no conozcas con certeza -- si no se te ocurre una reformulacion "
    "genuinamente distinta que valga la pena probar, responde EXACTAMENTE "
    "con la misma consulta original sin cambios. Responde SOLO con la "
    "consulta (original o reformulada), una sola linea, sin explicaciones, "
    "sin comillas, sin markdown."
)
