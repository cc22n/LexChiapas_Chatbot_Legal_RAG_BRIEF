# LexChiapas - Chatbot Legal RAG (Telegram + WhatsApp)

> **Estado:** APROBADO
> **Fecha de aprobacion:** 2026-06-25
> **Tipo:** Proyecto de portafolio (RAG + Chatbot + NLP)
> **Objetivo:** Demostrar skills de RAG, embeddings, Celery, y chatbots que las
> vacantes de IA piden constantemente
> **Tema:** Leyes y reglamentos del Estado de Chiapas (documentos publicos)

---

## 1. Descripcion del Proyecto

Chatbot que responde preguntas sobre leyes y reglamentos de Chiapas usando RAG
(Retrieval Augmented Generation). El usuario pregunta en lenguaje natural via
Telegram (o WhatsApp), el sistema busca en los documentos legales los fragmentos
relevantes, y un LLM genera una respuesta fundamentada citando la fuente.

**Por que este proyecto para portafolio:**
Las vacantes de IA piden constantemente "construir chatbots con RAG". Este
proyecto demuestra TODO lo que buscan: embeddings, busqueda por similitud
(dense) y por dispersion (sparse/BM25), vector stores, chunking de documentos,
Celery para tareas en background, integracion con plataformas de mensajeria, y
manejo de un dominio real (legal) donde la precision importa.

**Por que el tema legal:**
Los documentos legales son publicos, densos, estructurados, y tienen demanda
real de consulta. La gente comun no entiende el lenguaje legal; un asistente
que traduce y explica leyes es util de verdad. Ademas demuestra que sabes
manejar documentos complejos con precision.

**IMPORTANTE - Disclaimer legal:**
El bot NO da asesoria legal profesional. Informa y explica lo que dicen las
leyes citando la fuente, pero SIEMPRE aclara que no sustituye a un abogado.
Esto se deja MUY claro en cada respuesta relevante y en el mensaje de bienvenida.

---

## 2. Datos Disponibles (Verificado)

Fuentes oficiales de leyes de Chiapas, publicas y descargables:

| Fuente | Contenido | Formato | URL |
|---|---|---|---|
| Congreso del Estado de Chiapas | Legislacion vigente completa | HTML/PDF | web.congresochiapas.gob.mx/trabajo-legislativo/legislacion-vigente |
| Consejeria Juridica de Chiapas | Leyes, decretos, reglamentos, lineamientos, acuerdos | PDF | consejeriajuridica.chiapas.gob.mx/MarcoJuridico |
| Justia Mexico (Chiapas) | Leyes estatales | HTML/PDF | mexico.justia.com/estatales/chiapas/leyes |
| ASE Chiapas | Leyes especificas en PDF | PDF | asechiapas.gob.mx/download/leyes |

Todo es data abierta y publica. Ideal para RAG.

**Estrategia de alcance:** Empezar con UN area del derecho o un conjunto acotado
de leyes (ej: leyes municipales, o derechos del ciudadano, o transparencia) para
validar el sistema. Despues expandir a mas leyes. No cargar TODO desde el inicio.

---

## 3. Conceptos Tecnicos que Demuestra (los que piden las vacantes)

| Concepto | Que es | Como se usa aqui |
|---|---|---|
| RAG | Retrieval Augmented Generation | El corazon del proyecto |
| Embeddings | Texto convertido a vectores | Representar chunks de leyes |
| Dense search | Busqueda por similitud semantica (cosine) | Encontrar fragmentos relevantes por significado |
| Sparse search (BM25) | Busqueda por dispersion/keywords | Encontrar por terminos legales exactos |
| Hybrid search | Combinar dense + sparse | Lo mejor de ambos (semantico + exacto) |
| Chunking | Partir documentos en fragmentos | Dividir leyes en articulos/secciones |
| Vector store | Base de datos de vectores | Guardar embeddings (ChromaDB) |
| Reranking | Reordenar resultados por relevancia | Mejorar la calidad de los fragmentos recuperados |
| Similarity threshold | Umbral minimo de similitud | Descartar chunks poco relevantes (anti-alucinacion) |
| Top-K | Traer solo los K mejores resultados | Menos ruido, menos alucinacion |
| Grounding / faithfulness | Obligar al LLM a apegarse a lo recuperado | Si nada supera el umbral, responde "no encontre" |
| Celery workers | Tareas en background programadas | Ingesta y actualizacion de leyes |
| Citations | Citar la fuente | Cada respuesta cita la ley y articulo |

---

## 4. Stack Tecnologico

| Capa | Tecnologia | Justificacion |
|---|---|---|
| Backend / API | FastAPI (Python 3.11+) | Async, consistente con tus proyectos |
| Base de datos | PostgreSQL (psycopg v3) | Conversaciones, metadata, logs Y vectores |
| Vector store | pgvector (extension de PostgreSQL) | Embeddings + dense search, TODO en una sola DB |
| Sparse search | BM25 (rank_bm25) o PostgreSQL full-text | Busqueda por keywords legales |
| Embeddings | NVIDIA NIM (NV-Embed) via API | Vectorizar texto, gratis, no carga la PC |
| LLM | NVIDIA NIM (MiniMax M2.7 / DeepSeek 3.2 / GLM 5.1) | Generar respuestas, gratis, multi-modelo |
| Orquestacion RAG | LangChain | Chains de RAG, retrievers |
| Task Queue | Celery + Redis | Ingesta de documentos en background |
| Scheduler | Celery Beat | Actualizar leyes periodicamente |
| Bot Telegram | python-telegram-bot | Canal principal |
| Bot WhatsApp | OpenWA / Baileys / whatsapp-web.js | Canal secundario (fase posterior) |
| PDF parsing | pypdf / pdfplumber | Extraer texto de PDFs legales |
| Cache | Redis | Cache de respuestas frecuentes |

### Notas de entorno Windows/PowerShell:
- Archivos Python: ASCII puro (sin acentos, tildes, emojis)
- Usar psycopg v3 (no psycopg2)
- `--break-system-packages` en pip installs donde sea necesario

### NVIDIA NIM - Proveedor de modelos (embeddings + LLM)

Se usa NVIDIA NIM (build.nvidia.com) como proveedor principal de modelos:

**Ventajas:**
- Free tier permanente, sin tarjeta de credito (~40 RPM, ampliable a 200)
- Modelos de embeddings (NV-Embed) Y de generacion (MiniMax M2.7, DeepSeek 3.2,
  GLM 5.1, Qwen, Llama 4, etc.)
- Todo corre en servidores de NVIDIA: la PC del usuario NO hace trabajo pesado
- Compatible con el SDK de OpenAI: solo cambiar base_url a
  https://integrate.api.nvidia.com/v1 y usar la key nvapi-
- Cambiar de modelo es cambiar una linea (el nombre del modelo)
- Integra directo con LangChain (endpoint OpenAI-compatible)

**Advertencias (importante para el diseno):**
- El catalogo de modelos CAMBIA: pueden deprecar modelos con pocos dias de aviso.
  Por eso el sistema debe ser MODEL-FLEXIBLE: fallback multi-modelo configurable
  via JSON para cambiar de modelo sin tocar codigo si uno desaparece
- Es para desarrollo/testing/portafolio, NO para produccion con usuarios reales
  masivos. Para uso personal y demo de portafolio es ideal
- Si algun modelo da error 403, hay que registrarse para esa familia de modelo
  en su pagina (Try API)

**Configuracion de fallback (ai_config.json):**
Orden sugerido de modelos LLM (todos en NVIDIA NIM):
1. MiniMax M2.7 (fuerte, compite con modelos premium)
2. DeepSeek 3.2 (bueno para razonamiento)
3. GLM 5.1 (multilingue, bueno para espanol)
Si NVIDIA falla por completo, fallback opcional a Gemini free tier.

---

## 5. Arquitectura RAG

```
INGESTA (Celery, en background)
================================
[PDFs/HTML de leyes] -> [Parser: extraer texto]
                              |
                              v
                    [Chunking: partir en articulos/secciones]
                    (respetar estructura legal: Titulo > Capitulo > Articulo)
                              |
                              v
                    [Generar embeddings de cada chunk]
                              |
                              v
                    [Guardar en ChromaDB (vectores) +]
                    [Metadata en PostgreSQL: ley, articulo, fecha]
                              |
                              v
                    [Indice BM25 para sparse search]


CONSULTA (tiempo real)
======================
[Usuario pregunta en Telegram/WhatsApp]
              |
              v
[Bot recibe mensaje]
              |
              v
[HYBRID SEARCH:]
   - Dense: embeddings + cosine similarity (semantico) via pgvector
   - Sparse: BM25 (keywords legales exactos)
   - Combinar candidatos
              |
              v
[THRESHOLD: descartar lo que este por debajo del umbral de similitud]
   - Si NADA supera el umbral -> "No encontre informacion sobre eso"
   - Esto es la clave anti-alucinacion
              |
              v
[RERANKING: reordenar los que pasaron por relevancia real]
              |
              v
[TOP-K: quedarse con los 3-5 mejores]
              |
              v
[LLM (NVIDIA NIM: MiniMax/DeepSeek/GLM) genera respuesta (GROUNDING):]
   - Usa SOLO los chunks recuperados (no inventa)
   - Si los chunks no responden bien, lo admite (no fuerza respuesta)
   - Cita la ley y el articulo
   - Explica en lenguaje simple
   - Agrega disclaimer (no es asesoria legal)
              |
              v
[Respuesta enviada al usuario con la cita]
              |
              v
[Guardar conversacion en PostgreSQL]
```

---

## 6. El Reto Clave: Chunking de Documentos Legales

Los documentos legales tienen estructura jerarquica (Titulo > Capitulo >
Seccion > Articulo). Un chunking ingenuo (partir cada 500 caracteres) rompe
esta estructura y produce respuestas malas.

**Estrategia de chunking legal:**
- Respetar la unidad natural: cada ARTICULO es un chunk (o grupo de articulos
  relacionados si son cortos)
- Mantener metadata: a que ley pertenece, numero de articulo, titulo, capitulo
- Incluir contexto en cada chunk: "Ley X, Titulo Y, Articulo Z: [contenido]"
- Para articulos muy largos, partir pero manteniendo referencia al articulo padre
- Esto permite citas precisas: "Segun el Articulo 45 de la Ley de Desarrollo
  Constitucional de Chiapas..."

**Por que importa:** La calidad de las citas depende de esto. Un buen chunking
legal es lo que separa un chatbot serio de uno que da respuestas vagas.

---

## 7. Esquema de Base de Datos (PostgreSQL)

### Tabla: `documents`
ID, nombre de la ley, tipo (ley/reglamento/decreto), fecha_publicacion,
fecha_ultima_reforma, source_url, area_derecho, is_active, ingested_at

### Tabla: `chunks`
ID, document_id (FK), articulo_numero, titulo, capitulo, seccion, content (TEXT),
chunk_metadata (JSONB), embedding (vector, columna pgvector), created_at
Nota: con pgvector el vector vive en la MISMA tabla (columna tipo vector),
no en una base separada. La busqueda por similitud se hace con SQL:
`ORDER BY embedding <=> query_vector LIMIT k` y el threshold con
`WHERE 1 - (embedding <=> query_vector) > 0.75`

### Tabla: `conversations`
ID, platform (telegram/whatsapp), user_id, chat_id, started_at, last_message_at

### Tabla: `messages`
ID, conversation_id (FK), role (user/assistant), content, retrieved_chunks (JSONB),
llm_model, response_time_ms, created_at

### Tabla: `feedback`
ID, message_id (FK), rating (util/no_util), user_comment, created_at
(para mejorar el sistema por curacion humana)

### Tabla: `ingestion_logs`
ID, document_id, status, chunks_created, error_message, started_at, completed_at

---

## 8. Estructura del Proyecto

```
lexchiapas/
|-- app/
|   |-- main.py                     # FastAPI entry
|   |-- config.py
|   |-- database.py
|   |-- models/                     # SQLAlchemy models
|   |-- schemas/                    # Pydantic
|   |-- api/                        # Endpoints (webhook, health, admin)
|   |   |-- telegram_webhook.py
|   |   |-- whatsapp_webhook.py
|   |   |-- admin.py                # Gestionar documentos
|   |-- rag/
|   |   |-- chunker.py              # Chunking legal
|   |   |-- embeddings.py           # Generar embeddings
|   |   |-- retriever.py            # Hybrid search (dense + sparse) + threshold
|   |   |-- reranker.py             # Reranking + top-K
|   |   |-- generator.py            # LLM genera respuesta con citas
|   |   |-- rag_pipeline.py         # Orquestacion completa
|   |-- bots/
|   |   |-- base_bot.py             # Interfaz abstracta (para multi-plataforma)
|   |   |-- telegram_bot.py         # Implementacion Telegram
|   |   |-- whatsapp_bot.py         # Implementacion WhatsApp (fase posterior)
|   |-- llm/
|   |   |-- providers.py            # Gemini + fallback
|   |   |-- router.py
|   |-- workers/                    # Celery
|   |   |-- ingestion_tasks.py      # Ingesta de documentos
|   |   |-- update_tasks.py         # Actualizar leyes
|   |   |-- celery_app.py
|-- ingestion/                      # Scripts de descarga de leyes
|   |-- scrapers/
|   |   |-- congreso_scraper.py
|   |   |-- consejeria_scraper.py
|   |-- parsers/
|   |   |-- pdf_parser.py
|   |   |-- html_parser.py
|-- data/
|   |-- raw/                        # PDFs descargados
|   |-- processed/                  # Texto procesado
|-- tests/
|-- ai_config.json
|-- requirements.txt
|-- README.md
|-- CLAUDE.md
|-- .env.example
```

---

## 9. Capa de Abstraccion de Bots (multi-plataforma)

Como quieres Telegram primero y WhatsApp despues, disenar una interfaz comun
para que la logica RAG no dependa de la plataforma:

```
BaseBot (interfaz abstracta)
  - handle_message(user_id, text) -> response
  - send_message(chat_id, text)

TelegramBot(BaseBot)   <- fase 1
WhatsAppBot(BaseBot)   <- fase posterior
```

La logica RAG es identica; solo cambia el canal. Asi agregar WhatsApp despues
es trivial.

---

## 10. Fases de Desarrollo

### Fase 1: Ingesta + RAG core (Semana 1-3)
**Objetivo:** Pipeline RAG funcionando por consola (sin bot todavia).

**Tareas:**
- Setup FastAPI + PostgreSQL + pgvector (instalar la extension)
- Descargar un conjunto acotado de leyes de Chiapas (empezar con pocas)
- Parser de PDF/HTML
- Chunking legal (respetando estructura de articulos)
- Generar embeddings (NVIDIA NV-Embed via API) y guardarlos en columna pgvector
- Dense search (cosine similarity con pgvector) + threshold de similitud
- Generacion de respuesta con NVIDIA NIM (MiniMax/DeepSeek) + citas (grounding)
- Probar por consola: pregunta -> respuesta con cita

**Entregable:** RAG que responde preguntas legales por consola con citas.

### Fase 2: Hybrid Search + Calidad (Semana 4-5)
**Objetivo:** Mejorar la recuperacion con busqueda hibrida.

**Tareas:**
- Sparse search con BM25 (keywords legales)
- Combinar dense + sparse (hybrid)
- Reranking de resultados
- Mejorar prompts para respuestas fundamentadas
- Manejo de "no se encontro" (no inventar)
- Disclaimer legal en respuestas

**Entregable:** RAG con busqueda hibrida y respuestas de calidad.

### Fase 3: Bot de Telegram (Semana 6-7)
**Objetivo:** Chatbot funcional en Telegram.

**Tareas:**
- Capa de abstraccion BaseBot
- Bot de Telegram (python-telegram-bot)
- Webhook o polling
- Manejo de conversaciones (contexto)
- Guardar conversaciones en PostgreSQL
- Mensaje de bienvenida con disclaimer
- Comandos: /start, /ayuda, /areas (que leyes cubre)

**Entregable:** Bot de Telegram que cualquiera puede probar.

### Fase 4: Celery + Ingesta automatica (Semana 8-9)
**Objetivo:** Sistema que se actualiza solo.

**Tareas:**
- Celery + Redis + Celery Beat
- Tareas de ingesta en background
- Scraping programado de nuevas leyes/reformas
- Actualizacion del indice sin downtime
- Panel admin para gestionar documentos
- Sistema de feedback (util/no util)

**Entregable:** Sistema que mantiene las leyes actualizadas automaticamente.

### Fase 5: WhatsApp + Pulido (Semana 10-12)
**Objetivo:** Segundo canal y experiencia completa.

**Tareas:**
- Implementar WhatsAppBot (OpenWA o Baileys)
- Reusar toda la logica RAG (solo cambia el canal)
- Metricas de uso (preguntas mas comunes, satisfaccion)
- Mejorar por curacion humana (revisar feedback, ajustar)
- README profesional + demo
- Deploy (bot corriendo 24/7)

**Entregable:** Chatbot legal en Telegram Y WhatsApp, listo para portafolio.

---

## 11. Evaluacion de Viabilidad

| Criterio | Score | Notas |
|---|---|---|
| Tiempo de desarrollo | 7/10 | 10-12 semanas, cada fase funcional |
| Complejidad tecnica | 6/10 | RAG + hybrid search + Celery + multi-bot |
| Impacto en portafolio | 10/10 | Exactamente lo que piden las vacantes de IA |
| Costo | 10/10 | Datos gratis, NVIDIA NIM gratis (embeddings + LLM), no carga la PC |

**Veredicto: APROBADO**

---

## 12. Riesgos y Mitigaciones

| Riesgo | Prob. | Impacto | Mitigacion |
|---|---|---|---|
| Chunking legal mal hecho | Media | Alto | Respetar estructura de articulos, es lo mas importante |
| El LLM inventa leyes (alucinacion) | Media | Alto | RAG estricto: responder SOLO con chunks recuperados, citar siempre |
| Leyes desactualizadas | Media | Medio | Celery para actualizacion, mostrar fecha de la ley |
| Confundir al usuario (parece asesoria legal) | Media | Alto | Disclaimer claro y constante |
| Espanol legal complejo para embeddings | Baja | Medio | Modelo de embeddings multilingual bueno |
| Ban de WhatsApp (no oficial) | Media | Bajo | Telegram es el principal; WhatsApp es extra |

---

## 13. Por que este proyecto te consigue entrevistas

- **RAG es LA habilidad mas pedida** en vacantes de IA ahora mismo
- Demuestra el pipeline completo: ingesta, chunking, embeddings, hybrid search,
  reranking, generacion con citas
- Celery muestra que sabes de sistemas async y tareas en background
- Multi-plataforma (Telegram + WhatsApp) muestra abstraccion limpia
- Dominio legal muestra que manejas datos complejos donde la precision importa
- Un reclutador puede PROBAR tu bot en vivo (link de Telegram) = impacto inmediato
- Es un proyecto "productizable": se ve como algo real, no un ejercicio academico

---

## 14. Escalabilidad Futura (el "algo mas complejo" que mencionaste)

Una vez que domines este, el siguiente nivel seria:
- Multi-agente legal (un agente busca, otro analiza, otro redacta)
- Comparar leyes entre estados (federalismo)
- Generacion de documentos legales basicos (plantillas)
- Analisis de contratos (subir un PDF y que lo explique)
- Fine-tuning de un modelo con lenguaje legal mexicano
- RAG con grafo de conocimiento (relaciones entre leyes)

---

## 15. Contexto para el chat de ejecucion

**Recordatorios clave:**
- Windows/PowerShell: ASCII puro, psycopg v3, --break-system-packages
- Modelos: NVIDIA NIM (build.nvidia.com) para embeddings (NV-Embed) y LLM
  (MiniMax M2.7 / DeepSeek 3.2 / GLM 5.1). Gratis, API, no carga la PC.
  - base_url = https://integrate.api.nvidia.com/v1, key nvapi-
  - Compatible con SDK de OpenAI y LangChain
  - MODEL-FLEXIBLE: fallback multi-modelo via JSON (el catalogo NVIDIA cambia)
  - Limite ~40 RPM (suficiente para uso personal/portafolio)
- Vector store: pgvector (extension de PostgreSQL, TODO en una sola DB)
  - Instalar la extension pgvector en PostgreSQL (en Windows requiere un paso extra)
  - Los embeddings viven en una columna tipo vector en la tabla chunks
  - Busqueda: ORDER BY embedding <=> query LIMIT k
- THRESHOLD de similitud: descartar chunks por debajo del umbral (anti-alucinacion)
  - Si nada supera el umbral, el bot dice "no encontre informacion", NO inventa
- El CHUNKING legal es lo mas importante: respetar estructura de articulos
- RAG estricto (grounding): el LLM responde SOLO con lo recuperado, NUNCA inventa leyes
- SIEMPRE citar la ley y el articulo
- SIEMPRE disclaimer: no es asesoria legal profesional
- Empezar con pocas leyes para validar, luego expandir
- Telegram primero (API oficial, sin riesgo), WhatsApp despues
- Capa de abstraccion de bots para multi-plataforma
- Hybrid search (dense + sparse) da mejores resultados que solo uno
- Celery para ingesta y actualizacion en background
- Mejora por curacion humana (feedback), no auto-reentrenamiento

---

*Documento generado desde el chat de planificacion de ideas.*
*Nombre sugerido del proyecto: LexChiapas*
