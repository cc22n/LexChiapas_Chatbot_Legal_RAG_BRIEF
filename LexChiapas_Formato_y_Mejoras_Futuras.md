# LexChiapas - Formato de Salida (Obligatorio) + Mejoras RAG Futuras

## Contexto:
LexChiapas ya esta avanzando e incluye un frontend con chat y dashboard de
metricas (preguntas, fallas, observabilidad, para uso interno del desarrollador).
Este documento cubre: (1) una correccion OBLIGATORIA de formato de salida, y
(2) tres mejoras de RAG que quedan como AMPLIACION FUTURA, condicionadas a que
las fases actuales den buenos resultados.

**IMPORTANTE:** Revisar el codigo actual y adaptar. LexChiapas ya existe.

---

# PARTE 1 (OBLIGATORIO): Correccion de formato de salida (asteriscos)

## Problema:
Los LLM estan entrenados con Markdown, entonces meten asteriscos (`**negrita**`,
`*cursiva*`) por costumbre. Telegram y WhatsApp NO usan el mismo Markdown, asi
que esos asteriscos se muestran literalmente (ej: `**esto**`) y se ve mal.

## Solucion: dos capas (defensa en capas)

**Capa 1 - System Prompt:**
Instruir al LLM que responda en texto limpio, sin Markdown de asteriscos.
Ejemplo de instruccion: "Responde en texto plano y claro. No uses asteriscos,
negritas de Markdown ni simbolos de formato."
- Reduce ~90% de los casos
- PERO no es 100% confiable: el LLM a veces se le olvida, sobre todo en
  respuestas largas

**Capa 2 - Backend (la garantia):**
Despues de que el LLM responde, el codigo procesa el texto ANTES de enviarlo.
Esta capa SI es 100% confiable. Dos opciones:

Opcion A - Limpiar (texto plano puro):
- Eliminar los asteriscos y simbolos Markdown de la respuesta
- Simple y seguro

Opcion B - Convertir al formato de cada plataforma (mas elegante):
- En vez de perder el formato, traducirlo al que cada plataforma entiende
- Telegram: tiene modo MarkdownV2 o HTML propio (negrita con su sintaxis)
- WhatsApp: negrita con `*texto*` (un asterisco), cursiva con `_texto_`
- Asi las respuestas se ven bien formateadas en cada canal

## Recomendacion:
Usar AMBAS capas. System prompt reduce el problema, backend lo elimina.
Regla de oro: nunca confiar solo en el system prompt para algo que DEBE
cumplirse. El system prompt sugiere, el backend garantiza.

## Conexion con la arquitectura existente:
Esto encaja con la capa de abstraccion de bots (multi-plataforma). Cada bot
(Telegram, WhatsApp, y el frontend web) puede tener su propio formateador de
salida:
- El RAG genera la respuesta (contenido)
- Cada canal la formatea a su manera antes de enviar
- Telegram -> su Markdown; WhatsApp -> su sintaxis; Web -> HTML/Markdown normal

En el frontend web propio, el Markdown SI se puede renderizar normal (ahi no hay
problema de asteriscos porque el navegador lo renderiza bien). El problema es
solo en Telegram/WhatsApp.

---

# PARTE 2 (AMPLIACION FUTURA): Mejoras RAG condicionadas

Estas tres mejoras NO se implementan ahora. Se dejan documentadas para
ampliar DESPUES de que terminen las fases actuales (evolucion RAG: avanzado ->
agentico -> graph) Y si los resultados son buenos. Son refinamientos, no
esenciales.

---

## 2.1 Parent-Child Retrieval (busqueda padre-hijo)

**Que es:**
Buscar con fragmentos PEQUENOS (hijos) porque son mas precisos para el matching,
pero entregar al LLM el fragmento GRANDE (padre) que los contiene, para que
tenga contexto completo.

**Por que sirve para leyes:**
Resuelve el dilema "chunks chicos buscan mejor pero chunks grandes dan mejor
contexto". Buscas con una frase especifica de un articulo (hijo), pero le das
al LLM el articulo completo o la seccion entera (padre) para que no responda
con un pedazo suelto sin contexto.

**Como funciona:**
- Al indexar: partir cada seccion/articulo (padre) en fragmentos chicos (hijos)
- Guardar la relacion hijo -> padre
- Al buscar: matchear con los hijos (precision)
- Al responder: recuperar los padres correspondientes (contexto)

**Cuando implementar:** Si tras las fases actuales se nota que las respuestas
carecen de contexto o citan fragmentos sueltos.

---

## 2.2 Reranking con puntuacion (cross-encoder o LLM-as-judge)

**Que es:**
Despues de que la busqueda trae N candidatos (ej: 20), un segundo modelo los
PUNTUA uno por uno segun que tan relevantes son de verdad a la pregunta, y
reordena. Se queda con los mejores.

**Dos sabores:**
- Cross-encoder: modelo especializado en puntuar pares (pregunta, chunk).
  Rapido y preciso. NVIDIA NIM tiene modelos de reranking.
- LLM-as-a-judge: un LLM barato lee la pregunta y cada chunk y asigna
  relevancia (ej: 8/10). Mas flexible pero gasta mas tokens.

**Nota:** LexChiapas ya tiene un reranking basico contemplado. Esto seria
mejorarlo a un cross-encoder real o LLM-as-judge.

**Cuando implementar:** Si se nota que a veces los chunks mas relevantes no
quedan en el top y el reranking basico no basta.

---

## 2.3 Correccion/normalizacion de la pregunta (query correction)

**Que es:**
Usar un modelo barato para corregir ortografia y redaccion de la pregunta ANTES
de generar el embedding. Si el usuario escribe mal, el embedding sale raro y no
matchea bien.

**Ejemplo:**
- Usuario: "kuales son las multaz del agwa"
- Corregido: "cuales son las multas del agua"
- El embedding de la version corregida matchea mucho mejor

**Por que es relevante aqui:**
En WhatsApp/Telegram la gente escribe rapido y con errores. Un corrector barato
mejora mucho la recuperacion con usuarios reales.

**Relacion con lo ya planeado:**
Esto es una variante del query rewriting (que ya esta en la Fase 1 de la
evolucion RAG). Se puede integrar como un paso de limpieza dentro del query
rewriting: primero corregir ortografia, luego reescribir a lenguaje legal.

**Cuando implementar:** Si se nota que usuarios reales escriben con muchos
errores y eso degrada la busqueda.

---

## Resumen de prioridades:

| Item | Estado |
|---|---|
| Correccion de asteriscos (system prompt + backend) | OBLIGATORIO - implementar |
| Parent-Child Retrieval | Futuro - si hace falta contexto |
| Reranking con puntuacion (cross-encoder/LLM-judge) | Futuro - si el reranking basico no basta |
| Correccion de preguntas (ortografia) | Futuro - si usuarios escriben con errores |

Las 3 mejoras futuras se evaluan DESPUES de terminar las fases actuales
(evolucion RAG) y solo si los resultados justifican agregarlas. No sobre-
ingenierizar: agregar solo lo que los datos del dashboard muestren que hace falta.

---

## Recordatorios para el chat de ejecucion:
- Windows/PowerShell: ASCII puro, psycopg v3, --break-system-packages
- LexChiapas ya existe (con frontend + dashboard de metricas): revisar y adaptar
- La correccion de asteriscos es OBLIGATORIA: system prompt + limpiador backend
- Cada canal (Telegram/WhatsApp/Web) formatea la salida a su manera
- En el frontend web el Markdown se renderiza normal (no hay problema ahi)
- Las 3 mejoras RAG son FUTURAS y condicionadas a buenos resultados
- Usar el dashboard de metricas para decidir que mejora futura vale la pena
- No sobre-ingenierizar: el proyecto ya esta solido
