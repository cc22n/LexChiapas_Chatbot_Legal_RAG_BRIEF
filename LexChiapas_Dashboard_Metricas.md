# LexChiapas - Requisitos del Dashboard de Metricas

## Contexto:
LexChiapas ya tiene un frontend con chat y un dashboard de metricas (para uso
interno del desarrollador). Este documento define QUE metricas no pueden faltar
(indispensables) y cuales serian buenas (deseables). El agente debe revisar que
ya tiene el dashboard actual y agregar lo que falte.

**El objetivo:** Los numeros convencen en la entrevista. Cuando un reclutador
pregunte "que tan bueno es tu RAG?", hay que tener datos concretos, no
"se siente bien".

**IMPORTANTE:** Revisar el dashboard actual primero, comparar contra esta lista,
y agregar lo que falte. No duplicar lo que ya existe.

---

## Las dos familias de metricas

1. **Metricas de CALIDAD del RAG:** que tan bien recupera y responde (lo que
   impresiona tecnicamente en entrevista)
2. **Metricas OPERATIVAS:** uso, costo, velocidad (lo que muestra que piensas
   en produccion)

---

# INDISPENSABLES (no pueden faltar)

## Calidad del RAG

**1. Precision de recuperacion (retrieval)**
- De las preguntas hechas, en cuantas el sistema recupero chunks relevantes
- Se mide contra un golden dataset (preguntas con respuesta correcta conocida)
- Metrica clave: "en X% de las preguntas, el chunk correcto estuvo en el top-K"

**2. Tasa de respuestas fundamentadas vs "no encontre"**
- Cuantas preguntas se respondieron con cita vs cuantas dieron "no encontre"
- Un balance sano: si casi todo es "no encontre", el threshold esta muy alto
  o faltan datos. Si nunca dice "no encontre", puede estar alucinando

**3. Tasa de fallas / preguntas sin respuesta**
- Preguntas que el sistema no pudo responder bien
- Esto ya lo mencionaste que mide. Es oro para saber donde mejorar

**4. Preguntas mas frecuentes**
- Que temas legales pregunta mas la gente
- Sirve para saber que leyes priorizar y donde enfocar

## Operativas

**5. Latencia (tiempo de respuesta)**
- Cuanto tarda el sistema en responder (promedio y percentiles)
- Separar: tiempo de busqueda vs tiempo de generacion del LLM
- Los reclutadores valoran que midas performance

**6. Uso de tokens / costo por consulta**
- Cuantos tokens gasta cada consulta
- Aunque NVIDIA NIM sea gratis, mostrar que mides costo es senal de madurez
- Util para justificar decisiones (ej: "el clasificador de intencion ahorra X%")

**7. Volumen de consultas**
- Cuantas preguntas por dia/semana
- Tendencia de uso en el tiempo (grafica)

**8. Tasa de guardrails activados**
- Cuantas preguntas fueron bloqueadas por estar fuera de tema
- Muestra que el anti-scope-creep funciona (conecta con el problema McDonald's)

---

# DESEABLES (suman mucho pero no son criticas)

## Calidad avanzada

**9. Feedback del usuario (util / no util)**
- Boton de pulgar arriba/abajo en cada respuesta
- Tasa de satisfaccion
- Las respuestas peor calificadas son las que hay que revisar

**10. Score de similitud promedio de los chunks recuperados**
- Que tan "seguros" son los matches (que tan cerca del umbral)
- Si el promedio es apenas arriba del threshold, la calidad es dudosa

**11. Distribucion de scores (grafica)**
- Histograma de que tan relevantes fueron los chunks
- Ayuda a calibrar el threshold optimo

**12. Metricas tipo RAGAS (si se implementa evaluacion formal)**
- Faithfulness: la respuesta se apega a los chunks (no alucina)
- Answer relevancy: la respuesta responde la pregunta
- Context precision: los chunks recuperados son relevantes
- Context recall: se recupero toda la info necesaria
- Estas son las metricas estandar de la industria para RAG

## Operativas avanzadas

**13. Fallback de modelos activado**
- Cuantas veces se uso el modelo primario vs el fallback
- Util con NVIDIA NIM (por si un modelo falla o se depreca)

**14. Errores del sistema**
- Fallas de API, timeouts, errores de parsing
- Log de errores para debugging

**15. Cobertura de la base de conocimiento**
- Cuantas leyes/articulos hay indexados
- Que areas del derecho estan cubiertas y cuales no

**16. Conversaciones por plataforma**
- Cuantas vienen de Telegram vs WhatsApp vs web
- Util para saber que canal usa mas la gente

---

# VISUALIZACIONES SUGERIDAS PARA EL DASHBOARD

- Grafica de linea: volumen de consultas en el tiempo
- Grafica de barras: preguntas mas frecuentes (top 10 temas)
- Medidor/gauge: tasa de respuestas exitosas vs fallas
- Histograma: distribucion de scores de similitud
- Tabla: ultimas preguntas con su resultado (respondida/no encontre/bloqueada)
- Tarjetas de numeros grandes (KPIs): total consultas, latencia promedio,
  tasa de exito, tokens usados
- Grafica de barras: consultas por plataforma
- Lista: respuestas peor calificadas (para revisar)

---

# PRIORIDAD DE IMPLEMENTACION

| Metrica | Prioridad |
|---|---|
| Precision de recuperacion (golden dataset) | Indispensable |
| Tasa respondidas vs "no encontre" | Indispensable |
| Tasa de fallas | Indispensable |
| Preguntas mas frecuentes | Indispensable |
| Latencia | Indispensable |
| Tokens/costo por consulta | Indispensable |
| Volumen de consultas | Indispensable |
| Guardrails activados | Indispensable |
| Feedback usuario (util/no util) | Deseable |
| Score similitud promedio | Deseable |
| Distribucion de scores | Deseable |
| Metricas RAGAS | Deseable |
| Fallback de modelos | Deseable |
| Errores del sistema | Deseable |
| Cobertura de conocimiento | Deseable |
| Conversaciones por plataforma | Deseable |

---

## Lo mas importante para la entrevista:

Si tuvieras que elegir SOLO 3 numeros para presumir en una entrevista, serian:
1. **Precision de recuperacion** (ej: "recupera el chunk correcto en el 87% de
   los casos") - demuestra que el RAG funciona
2. **Latencia** (ej: "responde en promedio en 1.8 segundos") - demuestra
   performance
3. **Tasa de exito con feedback** (ej: "92% de respuestas marcadas como utiles")
   - demuestra calidad real

Estos 3 responden la pregunta clave: "tu RAG, que tan bueno es?" con numeros.

---

## Nota sobre el golden dataset (para medir bien):

Para medir precision de recuperacion se necesita un "golden dataset":
- 30-50 preguntas legales tipicas
- Con la respuesta correcta y el articulo/ley que la contiene
- Se corre el RAG contra este set y se mide cuantas acerto
- Este dataset tambien sirve para comparar entre las fases de evolucion
  (avanzado vs agentico vs graph): ver si cada fase realmente mejora los numeros

Crear el golden dataset es la unica tarea "manual" pero es lo que permite tener
numeros confiables. Vale totalmente la pena.

---

## Recordatorios para el chat de ejecucion:
- Windows/PowerShell: ASCII puro, psycopg v3, --break-system-packages
- Revisar el dashboard ACTUAL primero, agregar solo lo que falte
- Las 8 metricas indispensables son la base minima
- Crear un golden dataset (30-50 preguntas) para medir precision de recuperacion
- El golden dataset sirve tambien para comparar las fases de evolucion RAG
- Los 3 numeros clave para entrevista: precision recuperacion, latencia, satisfaccion
- No sobrecargar el dashboard: mejor pocas metricas claras que muchas confusas
