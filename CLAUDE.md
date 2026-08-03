# CLAUDE.md — LexChiapas (Chatbot Legal RAG)

Contexto persistente para trabajar en este proyecto. El brief completo esta en
`LexChiapas_Chatbot_Legal_RAG_BRIEF.md` — leelo si necesitas el detalle
completo de fases, riesgos, o justificaciones. Este archivo es el resumen
operativo para escribir codigo.

## Que es el proyecto

Chatbot (Telegram primero, WhatsApp despues) que responde preguntas sobre
leyes y reglamentos del Estado de Chiapas usando RAG. Proyecto de portafolio:
el objetivo es demostrar RAG, embeddings, hybrid search, Celery y bots de
mensajeria con precision de dominio legal.

**Regla de oro del dominio legal:** el bot NUNCA inventa leyes. Si nada supera
el umbral de similitud, responde "no encontre informacion sobre eso". Toda
respuesta que si tenga fundamento cita la ley y el articulo, y siempre incluye
el disclaimer de que no es asesoria legal profesional.

## Estado actual

El scaffold completo de `lexchiapas/` ya existe (FastAPI, modelos, pipeline
RAG, bots, Celery, scrapers/parsers) y compila, pero no ha corrido nunca
contra una DB o API key real. El roadmap detallado por fase, con checklist y
que subagente usar para cada tarea, vive en **`PLAN.md`** — leelo antes de
seguir trabajando y marca ahi el progreso.

## Stack

- **Backend:** FastAPI, Python 3.11+
- **DB:** PostgreSQL (psycopg v3, NO psycopg2) + extension **pgvector** para
  embeddings (vector vive en columna de la tabla `chunks`, no en DB separada)
- **Sparse search:** BM25 (rank_bm25) o full-text de PostgreSQL
- **Embeddings + LLM:** NVIDIA NIM (build.nvidia.com), SDK compatible con
  OpenAI: `base_url=https://integrate.api.nvidia.com/v1`, key `nvapi-...`
  - Embeddings: NV-Embed
  - LLM (orden de fallback sugerido): MiniMax M2.7 -> DeepSeek 3.2 -> GLM 5.1
  - El catalogo de NVIDIA cambia: el fallback DEBE ser configurable via
    `ai_config.json`, nunca hardcodeado
- **Orquestacion RAG:** LangChain
- **Colas:** Celery + Redis, Celery Beat para scheduling
- **Bots:** python-telegram-bot (Telegram, fase 1); OpenWA/Baileys (WhatsApp,
  fase posterior) detras de una interfaz `BaseBot` comun
- **Parsing:** pypdf / pdfplumber

## Convenciones de entorno (Windows/PowerShell)

- Archivos Python en **ASCII puro**: sin acentos, tildes ni emojis en el
  codigo (comentarios, strings, nombres). El contenido legal en espanol con
  acentos vive en datos/DB, no en el codigo fuente.
- Usar **psycopg v3**, nunca psycopg2.
- `pip install --break-system-packages` cuando el entorno lo requiera.
- pgvector en Windows requiere un paso extra de instalacion de la extension.

## Arquitectura RAG (resumen)

```
Ingesta:  documento -> parser -> chunking legal -> embeddings -> pgvector + metadata Postgres -> indice BM25
Consulta: pregunta -> hybrid search (dense pgvector + sparse BM25) -> threshold -> rerank -> top-K -> LLM grounded -> respuesta + cita
```

Invariantes que no se deben romper:
- **Threshold primero:** cualquier chunk por debajo del umbral de similitud
  (sugerido `1 - (embedding <=> query) > 0.75`) se descarta ANTES de generar
  respuesta.
- **Grounding estricto:** el LLM solo puede usar los chunks recuperados. Si no
  hay suficiente base, debe admitirlo, no rellenar con conocimiento propio.
- **Citas obligatorias:** ley + numero de articulo en cada respuesta con
  fundamento.
- **Disclaimer constante:** "no sustituye asesoria legal profesional" en el
  mensaje de bienvenida y en respuestas relevantes.

## El chunking legal es lo mas critico del proyecto

Los documentos tienen jerarquia Titulo > Capitulo > Seccion > Articulo. La
unidad de chunk natural es el **articulo** (agrupando articulos cortos
relacionados si hace falta), nunca un corte ciego por caracteres. Cada chunk
debe llevar metadata de a que ley/articulo/titulo/capitulo pertenece, y
preferiblemente el contexto inline ("Ley X, Titulo Y, Articulo Z: ..."). Un
chunking malo es el riesgo #1 del proyecto (ver seccion 12 del brief).

## Estructura de carpetas objetivo

```
lexchiapas/
|-- app/
|   |-- main.py, config.py, database.py
|   |-- models/            # SQLAlchemy
|   |-- schemas/            # Pydantic
|   |-- api/                # telegram_webhook.py, whatsapp_webhook.py, admin.py
|   |-- rag/                # chunker.py, embeddings.py, retriever.py, reranker.py, generator.py, rag_pipeline.py
|   |-- bots/               # base_bot.py, telegram_bot.py, whatsapp_bot.py
|   |-- llm/                # providers.py, router.py
|   |-- workers/            # celery_app.py, ingestion_tasks.py, update_tasks.py
|-- ingestion/
|   |-- scrapers/           # congreso_scraper.py, consejeria_scraper.py
|   |-- parsers/            # pdf_parser.py, html_parser.py
|-- data/
|   |-- raw/, processed/
|-- tests/
|-- ai_config.json
|-- requirements.txt
```

## Fuentes de datos (publicas, verificadas)

- Congreso del Estado de Chiapas — legislacion vigente (HTML/PDF)
- Consejeria Juridica de Chiapas — leyes/decretos/reglamentos (PDF)
- Justia Mexico (Chiapas) — leyes estatales (HTML/PDF)
- ASE Chiapas — leyes especificas (PDF)

Empezar con un area del derecho acotada para validar el sistema antes de
expandir a todo el catalogo de leyes.

## Skills disponibles (`.claude/skills/`)

- `/ingest-ley` — corre el pipeline de ingesta completo para una ley (parse,
  chunk, embed, guardar) y reporta cuantos chunks se crearon.
- `/test-rag-query` — corre una pregunta de prueba por el pipeline completo y
  muestra chunks recuperados, scores, y la respuesta final con cita.
- `/check-grounding` — audita una respuesta ya generada contra los chunks que
  la originaron para detectar alucinacion o citas incorrectas.
- `/add-nim-model` — agrega/reordena un modelo NVIDIA NIM en `ai_config.json`.

## Subagentes disponibles (`.claude/agents/`)

- `legal-chunker` — disena/revisa la logica de chunking legal y su output.
- `rag-quality` — prueba y ajusta retrieval (dense/sparse/hybrid, threshold,
  reranking, top-K) y verifica grounding/anti-alucinacion.
- `bot-integration` — implementa/prueba la capa `BaseBot` y los bots de
  Telegram/WhatsApp.
