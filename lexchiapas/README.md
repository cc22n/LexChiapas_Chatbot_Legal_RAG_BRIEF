# LexChiapas

Chatbot legal (RAG) sobre leyes y reglamentos del Estado de Chiapas. Ver el
brief completo y `CLAUDE.md` en la raiz del repositorio para arquitectura,
fases y convenciones; el detalle fase por fase con hallazgos y verificacion
real vive en `PLAN.md`. Este backend (FastAPI) sirve el bot de Telegram y la
API que consume el frontend web (`../lexchiapas-web/`).

## Setup

```bash
pip install -r requirements.txt --break-system-packages
cp .env.example .env   # llenar NVIDIA_API_KEY, DATABASE_URL, etc.
alembic upgrade head    # aplica el esquema (documents, chunks, conversations,
                         # messages, feedback, legal_relations, ingestion_logs)
```

PostgreSQL necesita la extension `pgvector` instalada antes de correr
migraciones (`CREATE EXTENSION vector;`). Las migraciones viven en
`alembic/` (adoptado tras el andamiaje inicial via SQLAlchemy directo, ver
`PLAN.md` para el detalle del baseline).

## Correr la API

```bash
uvicorn app.main:app --reload
```

En desarrollo, `FRONTEND_ORIGIN` acepta automaticamente tanto
`http://localhost:3000` como `http://127.0.0.1:3000` (ver `app/main.py`) --
el navegador los trata como origenes CORS distintos aunque apunten al mismo
puerto.

## Correr Celery

```bash
celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app beat --loglevel=info
```

## Tests

```bash
pytest tests/ --ignore=tests/test_rag_regression.py   # deterministas, rapidos
pytest tests/test_rag_regression.py                    # golden dataset (24
                                                         # preguntas), llama a
                                                         # la API real -- lento
                                                         # y con costo real
```

## Canales

**Telegram** es el canal en vivo (bot funcional, probado contra la API real).
**WhatsApp** no esta implementado a proposito: el core del bot
(`app/bots/base_bot.py`) ya esta diseñado desde el inicio como una interfaz
comun para poder agregar canales nuevos sin duplicar logica RAG, y
`app/bots/telegram_bot.py` es la unica implementacion concreta hoy. Se evaluo
agregar WhatsApp (via Baileys/OpenWA, ninguno con API oficial gratuita) y se
decidio no hacerlo: ambas opciones requieren un proceso Node.js aparte y
vincular un numero de telefono real por QR, con riesgo real de baneo por
automatizacion si corre 24/7 -- costo/riesgo operativo que no se justifica
para un proyecto de portafolio sin demanda real de usuarios en ese canal
todavia.

## Estado

Fases 0-8 completas (andamiaje, RAG core con hybrid search + reranker real +
cache semantico, guardrails de dos capas, memoria conversacional, bot de
Telegram, expansion del corpus, ingesta/actualizacion automatica via Celery,
RAG avanzado con query rewriting + HyDE, RAG agentico via LangGraph con
self-reflection, y GraphRAG sobre `legal_relations` para preguntas de
historial legal) -- ver `PLAN.md` para el detalle de cada fase, con
hallazgos reales y verificacion contra la DB/API en produccion (no solo
lectura de codigo).

- **Corpus:** 32 leyes/codigos activos (`documents.is_active=true`) de las
  146 catalogadas en el sitio del Congreso de Chiapas -- ver
  `LexChiapas_Leyes_Pendientes_Congreso.md` para el catalogo completo de
  pendientes y el criterio de priorizacion.
- **`ai_config.json` "agentic_rag.enabled"** controla si `/api/chat/web` y el
  bot de Telegram usan el pipeline lineal (`app.rag.rag_pipeline`) o el
  agente LangGraph (`app.rag.agent_pipeline`, decidir -> buscar -> generar,
  con reintento acotado de self-reflection) -- intercambiable sin tocar
  codigo, ver `app.bots.conversation_store.handle_turn`.
- **Golden dataset real** (24 preguntas, `app/evaluation/golden_dataset.py`,
  corrido via `tests/test_rag_regression.py` contra la API real, sin mocks):
  ultima corrida completa 23 passed / 1 xfail conocido.
- Fase de deploy (Railway/Render + Vercel) y WhatsApp (via `BaseBot`, ver
  abajo) quedan pendientes -- ver `PLAN.md` Fase 5/Fase D de
  `WEB_FRONTEND_PLAN.md` para el detalle de lo ya preparado.
