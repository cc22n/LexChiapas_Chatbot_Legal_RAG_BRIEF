# LexChiapas Web

Frontend Next.js (App Router) para LexChiapas: chat legal publico + dashboard
de metricas privado para el equipo. Consume la API FastAPI del backend
(`../lexchiapas/`) -- ver `CLAUDE.md` (raiz del repo) y
`WEB_FRONTEND_PLAN.md` para arquitectura y el detalle fase por fase.

## Paginas

- `/` -- chat legal publico (widget que llama a `POST /api/chat/web` del
  backend, sin login).
- `/login` -- acceso al dashboard privado.
- `/dashboard` -- resumen general de metricas.
- `/dashboard/calidad` -- grounding, benchmark del golden dataset, tecnicas
  de RAG avanzado (query rewriting, HyDE, reranking).
- `/dashboard/uso` -- volumen de conversaciones/mensajes.
- `/dashboard/performance` -- latencia y uso de modelos/fallback.
- `/dashboard/agente` -- trace del agente LangGraph (ruta elegida, reintentos
  de self-reflection) cuando `agentic_rag.enabled=true` en el backend.
- `/dashboard/guardrails` -- rechazos por Capa 1 (fuera de dominio) y Capa 2
  (grounding).
- `/explorar` -- explorador del corpus de leyes ingeridas.

## Setup

```bash
npm install
cp .env.local.example .env.local   # ver notas abajo
npm run dev
```

Abrir [http://127.0.0.1:3000](http://127.0.0.1:3000).

**Variables de entorno** (`.env.local`, ver `.env.local.example`):

- `NEXT_PUBLIC_API_BASE_URL` -- URL del backend FastAPI. En desarrollo local
  usar `http://127.0.0.1:8000`, **no** `localhost`: en este entorno Chrome
  puede resolver `localhost` a `::1` (IPv6) mientras `uvicorn` solo escucha
  en `127.0.0.1` (IPv4) por default, causando `Failed to fetch` aunque el
  backend si responda (ver `app/main.py` del backend, que ya acepta ambos
  origenes CORS en desarrollo por el mismo motivo).
- `ADMIN_SESSION_SECRET` -- secreto propio de Next.js (HMAC-SHA256) para
  firmar la cookie de sesion de `/dashboard`. Independiente del
  `SECRET_KEY` del backend. Generar uno real en produccion (ej.
  `openssl rand -hex 32`), nunca reusar el valor de ejemplo.

El backend debe estar corriendo (`uvicorn app.main:app --reload` en
`../lexchiapas/`) para que el chat y el dashboard tengan datos reales.

## Stack

Next.js (App Router) + TypeScript + Tailwind. Sin mocks: todo dato que se
muestra viene de un endpoint real del backend (`/api/chat/web`,
`/admin/metrics/*`) -- si un dato no esta disponible todavia, la UI lo deja
explicito en vez de inventar un placeholder.

## Deploy

Preparado para Vercel (frontend) + Railway/Render (backend + Postgres con
pgvector), pero no ejecutado todavia -- requiere credenciales del usuario en
esos servicios. Ver `WEB_FRONTEND_PLAN.md` Fase D para la investigacion de
plataforma ya hecha (Railway tiene template con pgvector preinstalado) y los
pasos concretos que faltan.
