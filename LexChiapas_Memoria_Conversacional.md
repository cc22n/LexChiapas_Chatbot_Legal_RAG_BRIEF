# LexChiapas - Nueva Funcionalidad: Memoria Conversacional (Persistencia)

## Problema que resuelve:
El chatbot debe seguir el hilo de una conversacion. Si un usuario pregunta algo
y luego hace una pregunta de seguimiento que depende de la anterior, el bot debe
correlacionarlas y no responder como si tuviera amnesia.

Ejemplo:
- Usuario: "Que dice la ley sobre el agua potable?"
- Bot: [responde sobre la Ley de Aguas de Chiapas]
- Usuario: "Y cuales son las multas?"  <- "las" se refiere al agua
- El bot debe entender que se refiere a las multas relacionadas con el agua

**IMPORTANTE:** LexChiapas ya esta avanzando. Revisar el codigo actual y adaptar.
Estas son necesidades, no especificaciones rigidas.

---

## Dos tipos de memoria (aclaracion conceptual)

**Memoria de corto plazo (contexto conversacional)** <- lo principal aqui
Recordar los ultimos mensajes de ESTA conversacion y pasarlos al LLM como
contexto. Es lo que hace que el bot siga el hilo. Simple y directo. NO necesita
embeddings.

**Memoria de largo plazo (semantica, con embeddings)** <- opcional/futuro
Para cuando hay tanta historia que no cabe en el contexto del LLM. Se convierten
conversaciones viejas en embeddings y se busca lo relevante (RAG sobre el
historial). Para LexChiapas es opcional porque la mayoria de consultas legales
son autocontenidas.

**Regla:** para seguir el hilo de una charla, basta con memoria de corto plazo.
La de embeddings es solo para historia muy larga.

---

## Arquitectura de memoria: PostgreSQL + Redis

Se usan las dos, cada una para algo distinto:

**PostgreSQL = memoria PERSISTENTE**
- Guarda cada mensaje (usuario y bot) con timestamp
- Si el usuario cierra el chat y vuelve mañana, la conversacion sigue ahi
- Ya esta en el esquema de LexChiapas (tablas conversations y messages)

**Redis = memoria de SESION rapida (cache)**
- Guarda los ultimos N mensajes de la conversacion activa para acceso instantaneo
- Evita consultar PostgreSQL en cada mensaje
- Se puede expirar (ej: sin actividad en 30 min, se limpia de Redis pero sigue
  en PostgreSQL)

**Como trabajan juntos:**
```
Mensaje nuevo llega
   |
   v
Los ultimos mensajes estan en Redis?
   SI -> los tomo de Redis (rapido)
   NO -> los cargo de PostgreSQL y los meto a Redis
   |
   v
Paso esos mensajes + la pregunta nueva al LLM (como contexto)
   |
   v
Guardo el nuevo intercambio en PostgreSQL (persistente) Y Redis (rapido)
```

---

## Ventana de contexto (detalle clave)

NO pasar los 200 mensajes de una conversacion larga al LLM (gasta muchos tokens
y hay un limite de contexto). Estrategias:

**Ventana deslizante (recomendada para LexChiapas):**
- Solo pasar los ultimos N mensajes (ej: ultimos 6-10)
- Suficiente para consultas legales, que no suelen ser charlas de 50 turnos

**Resumen (para conversaciones largas):**
- Cuando la conversacion crece, un LLM resume lo viejo en un parrafo
- Se mantiene el resumen + los ultimos mensajes literales

**Hibrido:**
- Resumen de lo antiguo + ultimos mensajes completos

Para LexChiapas: ventana deslizante de ultimos ~6-10 mensajes es suficiente.

---

## Interaccion con el RAG (importante)

La memoria y el RAG trabajan juntos pero son cosas distintas:
- La MEMORIA da el contexto de la conversacion (que se ha hablado)
- El RAG da el conocimiento de las leyes (que dicen los documentos)

Flujo combinado para una pregunta de seguimiento:
```
Usuario: "Y cuales son las multas?" (seguimiento)
   |
   v
[MEMORIA: recuperar contexto -> "estabamos hablando de agua potable"]
   |
   v
[Reformular la pregunta con contexto:]
   "cuales son las multas relacionadas con agua potable en Chiapas"
   (esto conecta con el query rewriting de la evolucion RAG)
   |
   v
[RAG: buscar en las leyes con la pregunta ya contextualizada]
   |
   v
[LLM: responder usando memoria + chunks recuperados]
```

Nota: la memoria mejora el query rewriting. Al reformular la pregunta de
seguimiento, se usa el contexto de la conversacion para hacerla auto-contenida
antes de buscar en el RAG.

---

## Esquema (ajustar al codigo actual)

Las tablas conversations y messages ya existen en el diseno de LexChiapas.
Verificar que messages guarde:
- conversation_id, role (user/assistant), content, timestamp
- Opcional: los chunks recuperados en cada respuesta (para debug)

Redis guarda por conversacion:
- key: conversation:{id}:recent_messages
- value: lista de los ultimos N mensajes
- TTL: ej. 30-60 min de inactividad

---

## Memoria de largo plazo con embeddings (OPCIONAL, futuro)

Solo si se quisiera que el bot recuerde algo de una conversacion de hace
semanas ("la vez pasada me dijiste del tramite X"):
- Convertir conversaciones viejas en embeddings
- Guardar en pgvector (ya se usa para el RAG)
- Buscar en el historial cuando sea relevante
- Esto es "RAG sobre el historial de conversaciones"

Para la primera version NO es necesario. La mayoria de consultas legales son
autocontenidas. Se agrega despues si se ve que hace falta.

---

## Recordatorios para el chat de ejecucion:
- Windows/PowerShell: ASCII puro, psycopg v3, --break-system-packages
- LexChiapas ya existe: revisar codigo actual, adaptar, no reescribir
- Memoria de corto plazo (ventana deslizante) es lo principal, no embeddings
- PostgreSQL = persistente; Redis = sesion rapida con TTL
- Ventana de ~6-10 mensajes para consultas legales
- La memoria alimenta el query rewriting (contextualizar preguntas de seguimiento)
- Memoria con embeddings (largo plazo) es OPCIONAL/futuro
- Guardar siempre en PostgreSQL para persistencia real
