# LexChiapas

Chatbot legal (RAG) que responde preguntas sobre leyes y reglamentos del
Estado de Chiapas, México, citando siempre la ley y el artículo exacto.
Disponible por Telegram, con un panel de administrador (Next.js) para
monitorear calidad, uso y performance del sistema.

**Regla de oro del dominio legal:** el bot nunca inventa leyes. Si nada
supera el umbral de similitud real, responde honestamente que no encontró
información, en vez de aproximar o alucinar una respuesta. Toda respuesta
con fundamento cita la ley y el artículo, y siempre incluye el disclaimer de
que no sustituye asesoría legal profesional.

## Por qué existe

Proyecto de portafolio para demostrar un sistema RAG de dominio legal de
punta a punta: chunking consciente de la jerarquía legal real
(Título > Capítulo > Sección > Artículo), hybrid search, reranking real,
un pipeline agéntico con auto-corrección, un grafo de relaciones legales
extraído del corpus, y evaluación medida contra un golden dataset — no solo
"conectar un LLM a una base de datos".

## Arquitectura

```
Ingesta:   documento -> parser -> chunking por articulo -> embeddings -> pgvector + metadata -> indice BM25
Consulta:  pregunta -> hybrid search (denso + BM25) -> umbral de similitud -> rerank -> top-K -> LLM con grounding -> respuesta + cita
```

- **Chunking legal**: la unidad natural es el artículo (nunca un corte
  ciego por caracteres), cada chunk lleva metadata de a qué ley/título/
  capítulo pertenece.
- **Hybrid search**: búsqueda densa (pgvector, embeddings) + BM25 (sparse),
  con umbral de similitud real aplicado ANTES de generar cualquier
  respuesta.
- **Reranking real**: NVIDIA NIM (`llama-nemotron-rerank`) con fallback a
  Jina y a una heurística local si ambos proveedores fallan.
- **RAG agéntico** (LangGraph): decide la ruta de búsqueda (general / por
  ley / artículo específico / historial de reformas), con auto-reflexión
  y reintento cuando el grounding inicial no es suficiente.
- **GraphRAG**: relaciones de reforma/derogación/adición entre leyes,
  extraídas por regex de los marcadores reales del Periódico Oficial
  (sin LLM), navegables en un explorador visual público.
- **Fallback multi-modelo**: orden de proveedores LLM configurable en
  `ai_config.json` (nunca hardcodeado), porque el catálogo de modelos
  gratuitos/baratos cambia seguido.
- **Guardrails en 3 capas**: fuera de alcance, intentos de jailbreak, y un
  segundo gate de grounding que audita la respuesta ya generada contra los
  chunks que la originaron.
- **Evaluación medida, no "a ojo"**: golden dataset de 24 preguntas reales
  contra el corpus, corrida bajo demanda (Celery) y con historial de
  resultados, no solo una corrida manual perdida en una terminal.

## Stack

| Capa | Tecnología |
|---|---|
| Backend | FastAPI, Python 3.11+ |
| Base de datos | PostgreSQL + pgvector (psycopg v3), migraciones con Alembic |
| Búsqueda | pgvector (densa) + BM25 (`rank_bm25`, sparse) |
| Embeddings / LLM | NVIDIA NIM (catálogo configurable, fallback a OpenAI/xAI/DeepSeek/Groq/Gemini) |
| Orquestación RAG | LangChain + LangGraph (pipeline agéntico) |
| Colas / async | Celery + Redis (ingesta, evaluación del golden dataset) |
| Bot | python-telegram-bot, detrás de una interfaz `BaseBot` reusable para otros canales |
| Panel de administrador | Next.js (App Router), Server Components, gráficas SVG a medida (sin librería de charts) |

## Estructura del repo

```
lexchiapas/       backend FastAPI + RAG + bot de Telegram + workers de Celery
lexchiapas-web/   frontend Next.js -- chat publico + panel de metricas para administradores
```

## Cómo correrlo localmente

Requiere PostgreSQL con la extensión `pgvector`, Redis, Python 3.11+ y
Node.js.

```bash
# Backend
cd lexchiapas
pip install -r requirements.txt
cp .env.example .env   # llenar NVIDIA_API_KEY, DATABASE_URL, ADMIN_API_KEY, etc.
uvicorn app.main:app --reload

# Frontend / panel de administrador (otra terminal)
cd lexchiapas-web
npm install
npm run dev   # abrir http://127.0.0.1:3000/login con la ADMIN_API_KEY del .env

# Bot de Telegram, modo polling local (otra terminal, opcional)
cd lexchiapas
python -m app.bots.telegram_polling

# Celery, solo si se va a correr ingesta o el golden dataset desde el panel
cd lexchiapas
celery -A app.workers.celery_app worker --loglevel=info
```

## Estado

Backend y frontend funcionales de punta a punta, verificados contra datos
reales (no mocks): ingesta de ~20 leyes del Estado de Chiapas, RAG híbrido
con reranking real, pipeline agéntico medido contra un golden dataset de 24
preguntas, panel de métricas con 5 vistas (uso, calidad, performance,
guardrails, agente), y un explorador público del grafo de relaciones
legales. Deploy 24/7 y cobertura del corpus completo del Congreso son
trabajo en progreso.

## Licencia

MIT
