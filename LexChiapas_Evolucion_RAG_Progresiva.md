# LexChiapas - Evolucion Progresiva del RAG (3 Fases)

## Objetivo:
Evolucionar LexChiapas de un RAG basico a un sistema de nivel senior, en 3
fases progresivas donde cada una se construye sobre la anterior (no la
reemplaza, la absorbe). Al final, un solo proyecto demuestra las 4 capas de
dominio RAG: basico -> avanzado -> agentico -> grafo.

**IMPORTANTE:** LexChiapas ya esta avanzando. Revisar el codigo actual y adaptar
estas evoluciones al patron existente. Cada fase debe funcionar por si sola
antes de pasar a la siguiente. Sin prisa.

**La narrativa de portafolio que esto construye:**
"Empece con RAG basico, optimice la recuperacion con HyDE y contextual
retrieval, lo converti en un agente que razona sobre como buscar, y agregue un
grafo de conocimiento para navegar las relaciones entre leyes." Muy pocos
candidatos pueden contar esta progresion sobre un mismo proyecto real.

---

## Punto de partida (lo que ya existe):
RAG lineal con: chunking legal, embeddings (NVIDIA NV-Embed), pgvector,
hybrid search (dense + sparse), threshold de similitud, reranking, grounding,
citas, guardrails, bot de Telegram. LLM via NVIDIA NIM.

---

# FASE 1: RAG Avanzado (mejorar la recuperacion)

Sigue siendo un pipeline lineal, pero mucho mas inteligente en como recupera.

## 1.1 Query Rewriting (reescritura de consulta)
El usuario pregunta en lenguaje coloquial; el sistema lo traduce a lenguaje
legal antes de buscar.

Ejemplo:
- Usuario: "me pueden correr sin pagarme?"
- Reescrito: "despido injustificado indemnizacion finiquito derechos trabajador"
- Busca con la version reescrita -> encuentra mucho mejor

Implementacion: un LLM barato reescribe la pregunta antes de la busqueda.
Guardar tanto la original como la reescrita.

## 1.2 HyDE (Hypothetical Document Embeddings)
En vez de buscar con la pregunta, el LLM genera una respuesta HIPOTETICA
(aunque sea imperfecta) y busca con ella.

Por que funciona: una respuesta se parece mas a un documento legal que una
pregunta. El embedding de la respuesta hipotetica matchea mejor con los chunks
reales.

Flujo:
- Pregunta -> LLM genera respuesta hipotetica -> embedding de esa respuesta ->
  buscar chunks similares a la respuesta hipotetica -> generar respuesta real
  con los chunks encontrados

## 1.3 Contextual Retrieval (tecnica de Anthropic)
Antes de indexar cada chunk, agregarle contexto que lo situa.

Ejemplo:
- Chunk original: "La multa sera de 100 a 500 UMAs"
- Chunk con contexto: "Este fragmento pertenece a la Ley de Aguas de Chiapas,
  Capitulo de Sanciones, Articulo 45. La multa sera de 100 a 500 UMAs"
- Se genera el contexto con un LLM al momento de indexar
- Reduce errores de recuperacion significativamente (Anthropic reporta hasta 49%)

## 1.4 Reranking mejorado
Usar un cross-encoder real para reordenar (no solo el reranking basico).
NVIDIA NIM tiene modelos de reranking disponibles.

**Entregable Fase 1:** Recuperacion notablemente mejor. Comparar metricas
antes/despues (que tan relevantes son los chunks recuperados).

---

# FASE 2: Agentic RAG (el RAG que razona)

Aqui el RAG deja de ser lineal. Se envuelve todo lo anterior en un AGENTE que
decide como proceder. Las tecnicas de Fase 1 se convierten en HERRAMIENTAS que
el agente usa cuando lo considera necesario.

## 2.1 El agente decide
En vez de siempre hacer el mismo pipeline, el agente razona:
- Necesito buscar informacion o puedo responder directo? (ej: "hola" no necesita RAG)
- Que herramienta uso: busqueda normal, HyDE, query rewriting?
- En que fuente busco: leyes estatales, reglamentos, decretos?
- La respuesta que tengo es suficiente o busco mas?

## 2.2 Auto-evaluacion (self-reflection)
Despues de recuperar, el agente se pregunta:
- "Estos chunks realmente responden la pregunta?"
- Si NO: reformula la query y busca otra vez (iterativo)
- Si la pregunta tiene varias partes: busca cada parte por separado
- Si despues de N intentos no encuentra: lo admite honestamente

## 2.3 Herramientas del agente
El agente tiene un conjunto de herramientas (las de Fase 1 + nuevas):
- search_laws(query) - busqueda hibrida normal
- rewrite_and_search(query) - con query rewriting
- hyde_search(query) - con HyDE
- search_by_law(law_name) - buscar dentro de una ley especifica
- get_article(law, number) - traer un articulo exacto
- check_answer_quality(question, chunks) - auto-evaluacion

## 2.4 Implementacion con LangGraph
LangGraph permite construir el flujo del agente como un grafo de estados:
- Nodo: analizar pregunta
- Nodo: decidir herramienta
- Nodo: buscar
- Nodo: auto-evaluar
- Nodo: buscar de nuevo (loop) o responder
- Nodo: generar respuesta final

Esto conecta directo con lo que aprenderias en ThreatChain (que tambien usa
LangGraph para el agente coordinador).

**Entregable Fase 2:** Un agente que razona sobre como buscar, se auto-evalua,
y busca iterativamente. Salto conceptual de "pipeline" a "agente".

---

# FASE 3: GraphRAG (navegar relaciones entre leyes)

El nivel frontera. En vez de tratar las leyes como chunks sueltos, se construye
un GRAFO de conocimiento con las relaciones entre ellas. Se agrega como otra
herramienta mas del agente (no reemplaza lo anterior).

## 3.1 Por que las leyes son perfectas para grafo
Las leyes estan llenas de relaciones:
- "Esta ley reforma a aquella"
- "Este articulo remite al articulo 45"
- "Este reglamento deriva de esta ley madre"
- "Esta ley fue derogada por este decreto"
- "Este articulo fue modificado por esta reforma en 2023"

Un RAG normal NO ve estas conexiones. Un GraphRAG SI las navega.

## 3.2 Construir el grafo
- Nodos: leyes, articulos, reglamentos, decretos, reformas
- Aristas (relaciones): reforma, deroga, remite_a, deriva_de, modifica
- Extraer las relaciones de los textos legales (con LLM + parsing)
- Guardar en un grafo (opciones: Neo4j, o un grafo en PostgreSQL, o NetworkX
  para empezar simple)

## 3.3 El poder del grafo
Ejemplo de pregunta que solo GraphRAG puede responder bien:
- "Que paso con la Ley de X?"
- GraphRAG navega: "Fue reformada en 2023 por el decreto Y. Su articulo 12
  remite a la Ley Z. El articulo 8 fue derogado."
- Un RAG normal solo encontraria el texto, no las relaciones

## 3.4 Integracion como herramienta del agente
El agente (Fase 2) ahora tiene una herramienta extra:
- query_graph(law) - navegar relaciones de una ley
- El agente decide: para preguntas de texto usa RAG normal; para preguntas
  sobre reformas/relaciones/historia de una ley, usa el grafo
- Puede combinar ambos: buscar el texto Y las relaciones

**Entregable Fase 3:** Sistema que navega relaciones legales. Nivel senior/frontera.

---

## Evaluacion de Viabilidad (evolucion completa)

| Criterio | Score | Notas |
|---|---|---|
| Tiempo de desarrollo | 5/10 | Cada fase 2-4 semanas, progresivas |
| Complejidad tecnica | 3/10 | Sube fase a fase; GraphRAG es lo mas complejo |
| Impacto en portafolio | 10/10 | Progresion completa de RAG, narrativa senior |
| Costo | 10/10 | NVIDIA NIM gratis, pgvector, grafo local |

**Veredicto: APROBADO (progresivo)**

---

## Orden recomendado y flexibilidad

- Hacer Fase 1 completa primero (mejora la base actual)
- Cuando funcione, pasar a Fase 2 (el salto grande)
- Fase 3 cuando quieras el nivel frontera (es opcional/avanzado)
- Cada fase es un logro independiente y demostrable
- Se puede pausar entre fases sin problema

## Conexion con tus otros proyectos:
- Fase 2 (LangGraph) refuerza lo de ThreatChain (mismo framework de agentes)
- El patron de agente que razona es transferible a cualquier proyecto de IA
- GraphRAG es una skill rara que casi nadie tiene

---

## Recordatorios para el chat de ejecucion:
- Windows/PowerShell: ASCII puro, psycopg v3, --break-system-packages
- LexChiapas ya existe: revisar codigo actual, adaptar, no reescribir
- Cada fase se construye SOBRE la anterior, no la reemplaza
- Fase 1: query rewriting + HyDE + contextual retrieval + reranking mejorado
- Fase 2: envolver todo en agente con LangGraph, tecnicas de Fase 1 = herramientas
- Fase 3: grafo de relaciones legales como herramienta extra del agente
- Modelos via NVIDIA NIM (model-flexible por si cambia el catalogo)
- Cada fase funcional por si sola antes de avanzar
- Medir mejoras entre fases (metricas de calidad de recuperacion)
