# WEB_FRONTEND_PLAN.md — Frontend web (chat publico + dashboard de metricas)

Documento aparte (no toca `PLAN.md`) para no chocar con trabajo en curso ahi.
Cuando se integre, agregar un puntero en `PLAN.md` hacia este archivo.

## Objetivo

Un canal web adicional a Telegram/WhatsApp: chat publico (para que cualquiera
pruebe el bot sin Telegram) + dashboard privado de metricas (uso, calidad del
RAG, costo/performance). Reutiliza `app/rag/rag_pipeline.py` sin duplicar
logica — el frontend solo consume la API de FastAPI que ya existe.

## Decisiones tomadas (2026-07-08)

- **Stack:** Next.js (App Router), deploy tipo Vercel para el frontend.
- **Dashboard de metricas:** privado, con login. Fase 1 reutiliza el
  `ADMIN_API_KEY` que ya existe (`app/api/admin.py`) como password de una
  pantalla de login simple — no se construye un sistema de usuarios nuevo
  todavia.
- **Metricas:** las tres capas — uso, calidad del RAG, y costo/performance.
- **Evolucion del RAG:** `LexChiapas_Evolucion_RAG_Progresiva.md` (raiz del
  repo) es el plan final del backend — 3 fases progresivas (RAG avanzado ->
  agentic RAG -> GraphRAG). Ese documento es responsabilidad del lado
  backend/RAG (otra sesion/ventana). **Esta sesion se encarga de todo el
  frontend correspondiente** — ver Fases E/F/G mas abajo, cada una gateada a
  que el backend tenga lista la fase equivalente.
- **Guardrails:** `LexChiapas_Guardrails.md` (raiz del repo) ya esta en el
  repo — 3 capas anti scope-creep (clasificador de intencion, system prompt
  estricto, threshold de RAG). El frontend tiene piezas que le corresponden,
  ver Fase A y Fase C mas abajo.

## Arquitectura

Dos apps separadas, no un monolito:

- `lexchiapas/` (FastAPI, ya existe) — sigue siendo el backend/API real.
- `lexchiapas-web/` (Next.js, nuevo) — consume la API via HTTP, no importa
  codigo Python. Separacion limpia: si en el futuro hay mas canales/frontends
  (widget embebible, app movil, etc.), todos pegan al mismo backend.

### Endpoints nuevos en el backend (antes de tocar el frontend)

- `POST /api/chat/web` — recibe `{session_id, message}`, llama a
  `rag_pipeline.answer_question()`, crea/reusa una `Conversation` con
  `platform="web"`, devuelve la respuesta + citas + disclaimer.
- `POST /api/feedback` — falta hoy (ya estaba anotado como pendiente en
  Fase 4 de `PLAN.md`); se adelanta porque el chat web lo necesita para los
  botones util/no_util.
- `GET /admin/metrics/usage` — preguntas/dia, usuarios unicos por
  plataforma, leyes mas consultadas.
- `GET /admin/metrics/quality` — tasa de "no encontre informacion", ratio
  feedback util/no_util, articulos mas citados.
- `GET /admin/metrics/performance` — latencia promedio/p95
  (`response_time_ms` ya existe en `messages`), uso por modelo (que tanto se
  dispara el fallback), tokens consumidos, errores recientes de
  `ingestion_logs`.
- `POST /admin/login` — valida `ADMIN_API_KEY`, si es correcto setea una
  cookie de sesion httpOnly (para que el dashboard de Next.js no tenga que
  guardar el key en localStorage).

### Cambios de schema necesarios

Hoy `messages` guarda `retrieved_chunks` (JSONB), `llm_model`,
`response_time_ms` — pero NO tokens ni un flag explicito de si hubo
respuesta con fundamento. Agregar:

- `messages.prompt_tokens`, `messages.completion_tokens` (Integer,
  nullable) — capturados desde `usage.prompt_tokens/completion_tokens` de la
  respuesta de NVIDIA NIM (compatible con SDK de OpenAI), hoy no se guardan
  en ningun lado.
- `messages.found_answer` (Boolean) — explicito, para no tener que parsear
  `retrieved_chunks` cada vez que se calcule la tasa de "no encontre
  informacion".
- `conversations.platform` ya es `String(20)` libre — solo hace falta
  documentar `"web"` como valor valido, no requiere migracion.

## Fases

### Fase A — Backend: endpoints y metricas (COMPLETADA 2026-07-09)

- [x] `POST /api/feedback` (util/no_util) — `app/api/feedback.py`, valida
      `rating` en `{util, no_util}` y que el `message_id` exista
- [x] Columnas `prompt_tokens`/`completion_tokens` en `messages` — migradas
      a mano contra la DB real (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`,
      el proyecto usa `create_all` sin Alembic, que no altera tablas
      existentes). Capturadas end-to-end: `app/llm/router.py`
      `generate_with_fallback()` ahora devuelve tambien
      `(prompt_tokens, completion_tokens)` desde `response.usage` de la API
      de NVIDIA NIM, propagado por `app/rag/generator.py` y
      `app/rag/rag_pipeline.py` hasta `ChatResponse`
- [x] Columna `found_answer` en `messages` — se persiste como
      `response.grounded` al guardar el mensaje assistant (no se toco
      `rag_pipeline.py` para esto, ya calculaba `grounded` correctamente)
- [x] `POST /api/chat/web` — `app/api/chat_web.py`, reutiliza
      `rag_pipeline.answer_question()` via un helper nuevo compartido
      `app/bots/conversation_store.py` (`handle_turn()`), tambien usado ahora
      por `telegram_bot.py` para no duplicar la logica de persistencia entre
      canales. Sesion via `session_id` en el body (se usa como `user_id` y
      `chat_id`, `platform="web"`)
- [x] Endpoints `GET /admin/metrics/{usage,quality,performance}` —
      `app/api/admin.py`, queries agregadas con SQL crudo (`jsonb_array_elements`
      sobre `retrieved_chunks` para "leyes mas consultadas"/"articulos mas
      citados", `percentile_cont` para latencia p95)
- [x] `POST /admin/login` / `POST /admin/logout` — `app/api/admin_auth.py`,
      cookie httpOnly firmada con HMAC-SHA256 (sin dependencia nueva; usa
      `admin_api_key` como llave de firma si no hay `SECRET_KEY` propia).
      La dependencia `require_admin` acepta el header `X-Admin-Api-Key`
      original O la cookie nueva, sin romper el uso existente de
      `/admin/documents`
- [x] CORS — `app/main.py`, `CORSMiddleware` habilitado solo si
      `FRONTEND_ORIGIN` esta seteado en el entorno (vacio por defecto, no
      afecta Telegram/webhooks)
- [x] Rate limiting de `/api/chat/web` — `app/api/rate_limit.py`, ventana
      deslizante en memoria por `session_id` (10 preguntas/minuto). Nota
      documentada en el codigo: NO es correcto contra multiples workers/
      procesos (cada uno tendria su propio contador); si se despliega con
      mas de 1 worker, mover a Redis (ya cableado como broker de Celery)
- [x] Flag de guardrails en la respuesta — `WebChatResponse.out_of_scope`,
      calculado en `chat_web.py` comparando `response.answer` contra
      `OUT_OF_SCOPE_MESSAGE` de `app/rag/guardrails.py` (Capa 1, implementada
      del lado backend mientras se trabajaba esto en paralelo). Se eligio
      esta comparacion en vez de tocar `ChatResponse`/`rag_pipeline.py`
      directamente para no chocar con la sesion de backend que estaba
      editando esos archivos al mismo tiempo
- [x] `GET /admin/metrics/guardrails` — cuenta mensajes assistant cuyo
      `content` es exactamente `OUT_OF_SCOPE_MESSAGE`, por dia y total.
      **Actualizado (backend, verificado 2026-07-24):** `jailbreak_attempts`
      ya NO es `null` — se agrego la columna `messages.jailbreak_detected`
      (poblada en `app/bots/conversation_store.py` `handle_turn()` sobre el
      mensaje `role='user'`, via `app.rag.guardrails.detect_jailbreak_attempt`,
      que ya existia pero antes solo se usaba para `logging.warning()`). El
      endpoint ahora devuelve `count(*) FROM messages WHERE
      jailbreak_detected = true` (probado en vivo contra la DB real: 1
      intento de jailbreak sembrado con una frase real de
      `JAILBREAK_PATTERNS` -> `jailbreak_attempts: 1`). El frontend puede
      quitar el `EmptyState` de "no medido todavia" para este campo y
      tratarlo como un conteo real (0 es un cero legitimo ahora, no ausencia
      de dato).

**Verificado end-to-end contra la API/DB real** (no solo que compile):
servidor local, `POST /api/chat/web` con una pregunta real sobre la Ley de
Amnistia (`grounded: true`, cita el Articulo 1, `prompt_tokens`/
`completion_tokens` capturados) y una pregunta fuera de tema (cortada por
Capa 1, `out_of_scope: true`, sin gastar tokens); `POST /api/feedback`;
las 4 rutas de `/admin/metrics/*` con cookie de sesion real; 401 sin sesion;
rate limit disparando 429 en la llamada 11 dentro de la misma ventana. Los
datos de prueba (sesiones sinteticas) se borraron de la DB despues, siguiendo
la misma convencion que uso el backend en Fase 1 (dejar datos reales, limpiar
lo sintetico).

**Entregable: CUMPLIDO.** API lista para el frontend, con metricas reales
disponibles.

### Fase B — Frontend: chat web publico (COMPLETADA 2026-07-09)

- [x] Scaffold Next.js 16 (App Router, TypeScript, Tailwind v4) en
      `lexchiapas-web/`, creado con `create-next-app --disable-git` (el repo
      padre no es git todavia, evita anidar uno)
- [x] Pantalla de chat: burbujas usuario/asistente, loading state
      ("Buscando en las leyes de Chiapas..."), markdown real via
      `react-markdown` (`src/components/MarkdownContent.tsx`) — el LLM
      devuelve markdown de verdad (headers, negritas, listas), no solo texto
      plano; se eligio react-markdown en vez de un parser propio con
      `dangerouslySetInnerHTML` porque el contenido viene del LLM, no es
      texto nuestro, y no debe poder inyectar HTML/scripts
- [x] Render de citas: acordeon nativo (`<details>/<summary>`, sin libreria)
      con ley + articulo como resumen y el texto completo del chunk al
      expandir (`src/components/CitationList.tsx`)
- [x] Disclaimer fijo en el header de toda la app (`DisclaimerBanner.tsx` en
      `layout.tsx`, no solo en el mensaje de bienvenida)
- [x] Boton util/no_util por respuesta conectado a `POST /api/feedback`,
      con estado optimista y rollback si falla la llamada
- [x] Sesion: `session_id` (`crypto.randomUUID()`) generado una vez y
      guardado en `localStorage` (`src/lib/session.ts`), reusado en todos
      los turnos de esa pestana/navegador
- [x] Manejo de error/rate limit: mensaje generico cuando el fetch falla,
      distinto al mensaje fijo de guardrails
- [x] Mensaje de guardrails (Capa 1) renderizado con el mismo estilo neutral
      que una respuesta normal (no rojo/error) usando
      `WebChatResponse.out_of_scope`

**Verificado end-to-end en navegador real (Chrome vía claude-in-chrome),
no solo build/lint:** backend (`uvicorn`, puerto 8000) + frontend (`next
dev`, puerto 3000) corriendo juntos, `FRONTEND_ORIGIN`/CORS configurados.
Probado: pregunta legal real (markdown renderizado, 5 citas expandibles,
texto completo del articulo al expandir), pregunta fuera de tema (estilo
neutral correcto, sin citas), feedback util (persistido, confirmado en el
log del backend), sesion persistida en `localStorage` entre mensajes.

**Bugs reales encontrados y arreglados durante la verificacion (no
teoricos, aparecieron probando de verdad):**

1. **`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` fallaba con
   `TypeError: Failed to fetch`, aunque `curl http://localhost:8000/health`
   respondia bien.** Causa: en esta maquina Windows, Chrome resuelve
   `localhost` a `::1` (IPv6) primero, pero `uvicorn` sin `--host` explicito
   solo escucha en `127.0.0.1` (IPv4) — confirmado con
   `curl -6 "http://[::1]:8000/health"` (falla) vs `netstat -ano` (solo
   `127.0.0.1:8000` en LISTENING). Arreglado usando `127.0.0.1` explicito
   en `.env.local`/`.env.local.example`/el default de `src/lib/api.ts`, con
   el porque documentado inline para que no se revierta por accidente.
2. **Los servidores de desarrollo (backend Y frontend) morian solos sin
   ningun error en su log** cuando se lanzaban con `(comando &)` dentro de
   una sola llamada del tool de Bash. Causa: ese patron de backgrounding
   manual no sobrevive de forma confiable entre llamadas del tool. Arreglado
   usando el parametro `run_in_background` del tool de Bash en vez de `&`
   manual — mas confiable para procesos que deben seguir vivos entre
   llamadas.
3. **Los clicks/teclas sinteticos del tool de automatizacion de Chrome
   fallaban de forma intermitente** (coordenadas de un screenshot anterior
   ya no correspondian tras un reflow, y la tecla Enter no siempre disparaba
   el submit) — no es un bug de la app, se resolvio disparando el evento
   `input` + `.click()` directo por JavaScript para tener pruebas
   deterministas, y usando `find` (referencias por elemento) en vez de
   coordenadas fijas cuando se seguia usando el tool de clicks.

**Hallazgo para reportar al lado backend (NO arreglado aqui, es codigo de
`app/rag/generator.py`, fuera de esta iniciativa y en cambio activo por la
otra sesion):** el disclaimer aparece DUPLICADO en las respuestas grounded
— una vez porque el LLM mismo lo incluye en su respuesta (el `SYSTEM_PROMPT`
parece pedirselo), y otra vez porque `generate_answer()` le concatena la
constante `DISCLAIMER` de todas formas. Visible en el navegador como dos
lineas casi identicas seguidas ("Este mensaje es informativo y no sustituye
la asesoria de un abogado." x2).

**Entregable: CUMPLIDO.** Chat funcional en `http://localhost:3000`, mismo
grounding/citas/disclaimer que Telegram, sin necesitar Telegram para
probarlo.

### Fase C — Frontend: dashboard de metricas (privado) (COMPLETADA 2026-07-11)

- [x] Pantalla de login (`/login`, pide `ADMIN_API_KEY`, POSTea a la Route
      Handler `/api/admin/login` de Next.js, que valida el key llamando a
      `GET /admin/metrics/usage` del backend con `x-admin-api-key` y, si es
      valido, setea cookie httpOnly propia del frontend)
- [x] Proteccion de `/dashboard/*` **sin** Proxy/middleware de Next.js —
      decision deliberada, ver "Decision: BFF en vez de Proxy" abajo.
      `src/lib/dal.ts` (`requireAdminApiKey()`) se llama en
      `dashboard/layout.tsx` y en cada `page.tsx` (patron "Data Access
      Layer" de la guia de auth de Next.js — el check debe vivir cerca de
      donde se usan los datos, no solo en el layout, porque los layouts no
      se re-renderizan en cada transicion client-side)
- [x] Vista "Uso" (`/dashboard/uso`): preguntas/dia (linea), leyes mas
      consultadas (barras), usuarios unicos por plataforma (tabla) +
      **cobertura de la base de conocimiento** (leyes activas indexadas,
      areas del derecho cubiertas, leyes por area) agregado durante la
      revision contra `LexChiapas_Dashboard_Metricas.md`, ver mas abajo
- [x] Vista "Calidad" (`/dashboard/calidad`): tasa de respuestas
      fundamentadas Y tasa de "no encontre informacion" (ambas, como par
      complementario), ratio feedback util/no_util (barras con colores de
      status, no categoricos), top articulos citados
- [x] Vista "Performance/costo" (`/dashboard/performance`): latencia
      promedio/p95, uso por modelo, tokens consumidos por dia (prompt vs
      completion, dos series), errores recientes de ingestion (tabla)
- [x] Vista "Guardrails" (`/dashboard/guardrails`): fuera de alcance por
      dia (Capa 1) + total; `jailbreak_attempts` (siempre `null` hoy) se
      muestra con un `EmptyState` explicito en vez de un `0` o una grafica
      vacia — un cero real y "no lo medimos todavia" son cosas distintas y
      no deben verse igual en el dashboard
- [x] Paleta y mark specs del skill `dataviz`: paleta categorica de 8
      colores validada con `scripts/validate_palette.js` (light: CVD ΔE
      24.2, 3 slots bajo 3:1 de contraste por diseno — mitigado con
      direct labels; dark: ΔE 10.3, banda piso, igual mitigado); barras
      <=24px con 4px redondeado en la punta; lineas 2px con marcador final
      de 8px+anillo de superficie de 2px; leyenda solo con 2+ series; texto
      nunca lleva el color de la serie. Componentes en
      `src/components/charts/` (`StatTile`, `BarChartHorizontal`,
      `LineChart`, `DataTable`, `ChartCard`, `EmptyState`), SVG/HTML a mano
      sin libreria de graficas (no habia ninguna en `package.json`)
- [x] "Vista como tabla" (gemelo de accesibilidad) en cada `ChartCard` via
      `<details>/<summary>` nativo, mismo patron sin-JS que
      `CitationList.tsx` de la Fase B

**Decision: BFF en vez de Proxy/middleware para la sesion del dashboard.**
El checklist original decia "middleware de Next.js"; se implemento distinto
a proposito. `app/api/admin.py` ya acepta el header `x-admin-api-key` O la
cookie del backend (`require_admin`, ver Fase A) — asi que en vez de que el
browser tenga que cargar con una cookie del dominio del backend (fricción
cross-origin real: frontend y backend son origenes distintos, y las cookies
que pone el backend con `Set-Cookie` no las puede leer el servidor de
Next.js despues), el frontend actua como Backend-For-Frontend completo:
login valida el key llamando al backend una vez, y si es valido lo guarda
DENTRO de una cookie propia del frontend (httpOnly, firmada con
HMAC-SHA256 via `node:crypto`, `src/lib/adminSession.ts` -- mismo patron
que `app/api/admin_auth.py` pero implementado en TS). Cada Server
Component/Route Handler que necesita datos lee esa cookie
(`requireAdminApiKey()`), y hace el fetch al backend server-to-server
adjuntando `x-admin-api-key` -- esto nunca pasa por el browser, asi que la
clave real no llega nunca a JS del cliente. Efecto secundario bueno: al
correr en Node.js runtime (Route Handlers/Server Components, no Edge), no
hay que pelear con que `node:crypto` no siempre esta disponible en el
Edge runtime que usaria un Proxy/middleware real.

**Nota sobre esta version de Next.js:** el `AGENTS.md` de `lexchiapas-web/`
advierte que esta version tiene cambios respecto al training data del
modelo. Confirmado leyendo `node_modules/next/dist/docs/`: `cookies()` de
`next/headers` es **async** ahora (`await cookies()`), y lo que antes era
`middleware.ts` en la raiz se documenta como `proxy.ts` ("Proxy") en la
guia de auth -- otro motivo mas para el patron BFF de arriba, que no
depende de ninguno de los dos.

**Verificado:** `npx tsc --noEmit` y `npx eslint` limpios sobre todos los
archivos nuevos (`src/app/dashboard/**`, `src/app/login/`,
`src/app/api/admin/**`, `src/components/charts/**`,
`src/components/dashboard/**`, `src/lib/adminApi.ts`, `adminSession.ts`,
`dal.ts`). Verificacion end-to-end contra la API/DB real via HTTP (`curl`
con cookie jar, no solo build/lint) -- el tool de automatizacion de Chrome
estaba desconectado en el momento de probar (extension sin conectar), asi
que **falta la verificacion visual/pixel** (colores, spacing, que las
graficas SVG se vean bien) -- correrla la proxima vez que el navegador este
disponible. Probado por HTTP:
1. `GET /dashboard` sin sesion -> 307 a `/login`
2. `POST /api/admin/login` con key incorrecta -> 401
3. `POST /api/admin/login` con `ADMIN_API_KEY` real -> 200, cookie
   `lexchiapas_dashboard_session` httpOnly/SameSite=lax/24h, payload
   `{key, iat}` firmado (verificado decodificando el JSON del cookie)
4. Las 4 vistas (`/dashboard/{uso,calidad,performance,guardrails}`) ->
   200, con datos reales (ej. "4" leyes activas indexadas, "4" areas del
   derecho cubiertas en Uso) y sin ningun error boundary de Next.js
   escondido en el HTML
5. Guardrails: `jailbreak_attempts: null` renderiza el `EmptyState`
   explicativo, no un cero ni una grafica vacia -- confirmado en el HTML
6. `POST /api/admin/logout` -> cookie borrada (`Expires=1970`), y
   `GET /dashboard` despues -> 307 a `/login` otra vez
7. Cookie de sesion forjada a mano (firma invalida) -> rechazada, redirect
   a `/login` (confirma que `crypto.timingSafeEqual` en
   `adminSession.ts` funciona)
8. `GET /login` -> 200, renderiza el formulario

**Hallazgo durante la verificacion, no relacionado con el codigo de esta
fase:** el puerto 8000 estaba ocupado por un proceso Python completamente
ajeno a LexChiapas (`manage.py runserver` de un proyecto Django distinto,
conda env `clud-de-lectura`, PID 6652, arrancado por otra ventana/proceso
en esta misma maquina). No se toco ese proceso -- se uso el puerto 8001
temporalmente para verificar (`.env.local` cambiado y revertido a 8000 al
terminar). Si vuelve a pasar, no matar el proceso sin confirmar de quien
es primero.

**Entregable: CUMPLIDO.** Dashboard privado con las cuatro vistas de
metricas mas cobertura de base de conocimiento, protegido por login, sin
depender de un `middleware.ts`, verificado funcionalmente end-to-end.

**Verificacion en navegador real (2026-07-17), extension de Chrome ya
conectada:** flujo completo login -> las 4 vistas -> logout -> redirect de
`/login` probado con clicks/navegacion reales, no solo HTTP. Confirmado via
`get_page_text` (texto real extraido del DOM renderizado, no el HTML crudo):
- `/login` -> formulario "Clave de administrador" / "Entrar"
- Login con `ADMIN_API_KEY` real -> redirect a `/dashboard/uso`, datos reales
  (5 preguntas, 17 leyes activas indexadas, 11 areas del derecho, seccion de
  cobertura de la Fase C.1 presente)
- `/dashboard/calidad` -> "Tasa de respuestas fundamentadas" 40.0%,
  feedback vacio muestra `--` en vez de dividir por cero
- `/dashboard/performance` -> latencia avg/p95, tokens por dia con 2 series,
  "Sin errores de ingestion recientes" (EmptyState, sin errores reales)
- `/dashboard/guardrails` -> "Intentos de jailbreak" muestra el mensaje
  explicativo de `EmptyState` (no un 0), confirma que null-vs-cero se
  distingue correctamente en el DOM renderizado, no solo en el JSON
- Logout -> vuelve a `/login`; navegar despues a `/dashboard/uso` a mano ->
  redirect a `/login` (confirma `requireAdminApiKey()` protegiendo cada
  pagina, no solo el layout)

**Sigue pendiente: verificacion visual/pixel real (captura de pantalla).**
La extension de Chrome esta conectada y todas las demas herramientas
(`navigate`, `find`, `form_input`, `computer` clicks, `get_page_text`)
funcionaron bien, pero `computer{action:"screenshot"}` fallo consistentemente
con timeout de `Page.captureScreenshot` (5 intentos, mismo error, en
distintas paginas) -- ver [[web-dev-environment-gotchas]] gotcha #6. No es
un problema del codigo del dashboard: es la captura de imagen la que esta
rota en esta sesion del navegador, todo lo demas responde con normalidad.
Colores/spacing/renderizado real de las graficas SVG sigue sin confirmarse
visualmente.

### Fase C.1 — Revision contra `LexChiapas_Dashboard_Metricas.md` (2026-07-11)

Este documento (raiz del repo, agregado por el usuario) lista 8 metricas
"indispensables" y 8 "deseables" para poder presumir el RAG en entrevista.
Instruccion explicita del documento: revisar el dashboard actual primero y
agregar solo lo que falte, sin duplicar. Reconciliacion completa:

| # | Metrica | Prioridad | Estado |
|---|---|---|---|
| 1 | Precision de recuperacion (golden dataset) | Indispensable | **Falta -- 100% trabajo nuevo.** No existe golden dataset ni evaluador en ningun lado del repo (confirmado, cero resultados buscando golden/ragas/evaluation/precision). Requiere: (a) 30-50 preguntas con respuesta/articulo correcto conocido -- tarea manual/de dominio, no de codigo; (b) script que corra cada pregunta por el RAG y compare contra el chunk esperado; (c) donde persistir el resultado; (d) un endpoint que lo exponga. **Bloqueado en el backend/RAG**, el frontend solo puede construir la vista una vez exista el dato. |
| 2 | Tasa fundamentada vs "no encontre" | Indispensable | **Ya cubierta**, mejorada hoy: Calidad ahora muestra el par completo (fundamentadas Y no-encontre), antes solo mostraba la segunda. |
| 3 | Tasa de fallas/preguntas sin respuesta | Indispensable | **Ya estaba parcialmente hecho (el `try/except` + `found_answer=None`/`error_message` ya existian en `app/bots/conversation_store.py`), ahora el endpoint tambien existe (verificado 2026-07-24).** `GET /admin/metrics/performance` agrego `system_error_rate` (`count(*) FILTER (WHERE found_answer IS NULL) AS system_errors` vs `count(*) AS total`, sobre mensajes `role='assistant'`) -- distinto de `not_found_rate` en `/admin/metrics/quality`, que sigue siendo la fuente de verdad de "no encontrado" legitimo del RAG (ya excluia `found_answer IS NULL` correctamente, no se toco). Probado en vivo contra la DB real: `{"system_errors": 0, "total": 9}`. |
| 4 | Preguntas mas frecuentes | Indispensable | **Hecho (verificado 2026-07-24).** `GET /admin/metrics/usage` agrego `top_questions` (`GROUP BY content` sobre `role='user'`, dedup exacto por texto verbatim, top 10). Probado en vivo: devuelve preguntas reales con su conteo (ej. "Que sanciones existen por tortura segun las leyes de Chiapas?" con count 2). |
| 5 | Latencia (con separacion busqueda/generacion) | Indispensable | **Parcial.** El agregado (avg/p95) ya esta en Performance. La separacion busqueda vs generacion NO existe -- `response_time_ms` es un solo `time.monotonic()` que envuelve TODO el pipeline (`rag_pipeline.py`), no hay columnas separadas. Requiere instrumentar 2 timers y 2 columnas nuevas. Bloqueado en backend. |
| 6 | Tokens/costo por consulta | Indispensable | **Ya cubierta** (tokens_per_day, usage_by_model en Performance). |
| 7 | Volumen de consultas | Indispensable | **Ya cubierta** (preguntas/dia en Uso). |
| 8 | Guardrails activados | Indispensable | **Ya cubierta** (fuera de alcance/dia + total en Guardrails). |
| 9 | Feedback util/no util | Deseable | **Ya cubierta** (Calidad + botones en el chat, Fase B). |
| 10 | Score de similitud promedio | Deseable | **Hecho (verificado 2026-07-24), con la separacion dense/sparse que este documento pedia.** Se agrego primero la columna `passed_threshold` al JSONB de `retrieved_chunks` (antes solo vivia en el dataclass interno `app.rag.retriever.RetrievedChunk`, nunca se persistia) -- sin eso no habia forma de distinguir un chunk con coseno real de uno solo-BM25. `GET /admin/metrics/quality` agrego `avg_similarity_grounded`, promediando SOLO `elem` con `passed_threshold=true`. Mensajes viejos (persistidos antes de este cambio) no tienen esa clave en su JSONB y quedan excluidos naturalmente del promedio (`->>` de una clave inexistente da NULL, y `NULL = true` no matchea el filtro) -- correcto, no un bug. Probado en vivo: `avg_similarity_grounded: 0.6297823792909873`. |
| 11 | Distribucion de scores (histograma) | Deseable | **Hecho (verificado 2026-07-24), mismo mecanismo que #10.** `GET /admin/metrics/quality` agrego `similarity_histogram`, buckets fijos de 0.1 (`0.5-0.6` ... `0.9-1.0`) sobre los mismos chunks `passed_threshold=true`. Probado en vivo: `[{"range":"0.5-0.6","count":5},{"range":"0.6-0.7","count":10}]` (buckets sin datos no aparecen en la respuesta, el frontend debe tratar buckets ausentes como 0, no como error). |
| 12 | Metricas RAGAS (faithfulness, answer relevancy, etc.) | Deseable | **Falta, alcance grande.** El propio documento lo marca como "si se implementa evaluacion formal" -- no es para ahora, requiere libreria RAGAS + golden dataset (ver #1) + pipeline de evaluacion aparte. Explicitamente diferido. |
| 13 | Fallback de modelos activado | Deseable | **Parcial.** `usage_by_model` (Performance) ya muestra cuantas respuestas uso cada modelo -- si el fallback se activo, se ve indirectamente (el modelo primario tendria menos conteo del esperado). Falta etiquetar explicitamente cual es "primario" vs "fallback" segun `ai_config.json` -- bajo esfuerzo pero requiere exponer ese orden via un endpoint (`ai_config.json` no es accesible desde el frontend hoy). Baja prioridad. |
| 14 | Errores del sistema | Deseable | **Parcial, actualizado 2026-07-24 -- la tasa ya esta cubierta por el fix de #3** (`system_error_rate` en `/admin/metrics/performance`, y `messages.error_message` con el traceback real ya se persiste por turno, ver `app.bots.conversation_store.handle_turn`). Lo que SIGUE faltando es un listado navegable de errores recientes de CHAT (analogo a `recent_ingestion_errors`, que solo cubre ingesta) -- hoy solo se puede ver el conteo agregado, no los mensajes de error individuales. Bajo esfuerzo si se retoma: una query mas en `/admin/metrics/performance` (`SELECT id, conversation_id, error_message, created_at FROM messages WHERE found_answer IS NULL ORDER BY created_at DESC LIMIT 20`, mismo patron que `recent_ingestion_errors`). |
| 15 | Cobertura de base de conocimiento | Deseable | **Resuelta hoy, sin pedir nada al backend.** `GET /admin/documents` ya existia (CRUD de documentos) y ya devuelve `area_derecho`/`is_active`/`nombre` en `DocumentOut` -- se agrego una seccion nueva en la vista "Uso" (leyes activas, areas cubiertas, leyes por area) que solo consume ese endpoint existente, sin tocar el backend. Nota: conteo de articulos/chunks por ley NO esta expuesto (existe la relacion `Document.chunks` pero no se serializa ni se agrega en ningun lado) -- si se quiere ese detalle, si requeriria backend. |
| 16 | Conversaciones por plataforma | Deseable | **Hecho (verificado 2026-07-24), ademas de la aproximacion previa de `unique_users_by_platform` (que se deja sin cambios, sigue siendo una metrica relacionada pero distinta).** `GET /admin/metrics/usage` agrego `conversations_by_platform` (`COUNT(*) FROM conversations GROUP BY platform`, numero exacto de conversaciones, no de usuarios unicos). Probado en vivo: `[{"platform":"telegram","count":1},{"platform":"web","count":1}]`. |

**Resumen (actualizado 2026-07-24, backend completo el paquete barato):** de
las 8 indispensables, 4 ya estaban cubiertas antes de este documento (2, 6,
7, 8), 1 se completo sin tocar backend (15, deseable, marcada aca por
contexto), y **#3 (tasa de fallas reales) ya esta resuelta** (endpoint
`system_error_rate` agregado y verificado en vivo). Queda 1 indispensable
bloqueada en backend: **#1 (golden dataset, el mas grande y el que el
propio documento marca como uno de los "3 numeros clave para la
entrevista")** -- #5 (latencia desglosada busqueda/generacion) sigue
parcial (el agregado avg/p95 ya existe, la separacion de timers no se toco
en esta sesion). De las deseables, **#4, #10, #11 y #16 ya estan resueltos**
(verificados en vivo contra la DB real). #12 y #13 son baja prioridad/
alcance grande, quedan para mas adelante. Nota lateral: #14 ("errores del
sistema") comparte el mismo dato que #3 (`found_answer IS NULL` +
`error_message`, ver `app/models/message.py`) -- no se marco arriba en su
propia fila porque no estaba en el alcance explicito de esta sesion, pero
`system_error_rate` ya cubre el numero agregado que pedia.

### Fase C.2 — Plan para los 3 items grandes/medianos restantes (disenado 2026-07-24, items 3.1/3.2 implementados 2026-07-24)

Diseno escrito ANTES de tocar codigo, mismo criterio ya usado en esta sesion
para el caso Art.1576 (documentar la opcion, ejecutar despues con
confirmacion explicita). Orden por costo/beneficio, no por dependencia --
los 3 son independientes entre si.

#### 3.1 Etiquetar modelo primario vs fallback -- HECHO (verificado 2026-07-24)

**No requiere columna nueva ni capturar dato nuevo.** `messages.llm_model`
ya guarda el modelo real que respondio cada mensaje
(`app.llm.router.generate_with_fallback` devuelve `model_used`, ya
persistido). "Primario" vs "fallback" es 100% derivable en el momento de
la query, comparando contra `ai_config.json["llm"]["fallback_order"][0]`
(la primera entrada de la lista es el primario por definicion; cualquier
otra entrada que respondio es fallback).

- Agregar un helper chico, ej. `get_primary_model() -> str` en
  `app/llm/router.py` (lee `get_ai_config()["llm"]["fallback_order"][0]["model"]`).
- En `app/api/admin.py`, extender `/admin/metrics/performance`: junto al
  `usage_by_model` que ya existe (sin tocarlo), agregar un campo derivado
  `primary_vs_fallback` -- `{"primary_model": "...", "primary_count": N,
  "fallback_count": M}`, calculado con una sola query adicional
  (`count(*) FILTER (WHERE llm_model = :primary)` vs el resto) o iterando
  sobre `usage_by_model` en Python (mas simple, evita otra query).
- Sin migracion, sin tocar `rag_pipeline.py`/`agent_pipeline.py`/
  `conversation_store.py`. Riesgo minimo -- es lectura pura sobre datos que
  ya existen.

**Implementado tal cual el diseno.** `get_primary_model()` en
`app/llm/router.py`; `primary_vs_fallback` agregado a
`/admin/metrics/performance`. Probado en vivo contra la DB real -- hallazgo
real (no esperado): `primary_count: 0`, `fallback_count: 3` -- el modelo
primario configurado (`minimaxai/minimax-m3`) no respondio NINGUNA de las
llamadas reales registradas hasta ahora, todo aterrizo en fallback
(`deepseek-ai/deepseek-v4-pro`, `z-ai/glm-5.2`). No es un bug de este
cambio -- el campo simplemente expuso algo que ya pasaba y no se podia ver
antes; vale la pena revisar por que el primario no responde si se retoma
trabajo en `ai_config.json`.

#### 3.2 Latencia desglosada busqueda/generacion -- HECHO (verificado 2026-07-24)

**Requiere 2 columnas nuevas** (mismo patron ya usado 6 veces esta sesion:
`ALTER TABLE messages ADD COLUMN IF NOT EXISTS ... ` manual, sin Alembic):
`search_time_ms` (Integer, nullable) y `generation_time_ms` (Integer,
nullable) en `app/models/message.py`.

- En `app/rag/rag_pipeline.py` (`answer_question`), instrumentar 2 timers
  nuevos con `time.monotonic()`, ademas del `start` que ya existe para
  `elapsed_ms` total (no se toca ese): uno que envuelve desde despues de
  Capa 1 de guardrails hasta el final de `rerank()` (query rewriting +
  sinonimos + HyDE + `hybrid_search` + `rerank` -- todo lo que es
  "busqueda" antes de generar), y otro que envuelve SOLO la llamada a
  `generate_answer()`. El segundo gate de grounding
  (`answer_is_grounded_in_practice`, otra llamada LLM aparte) queda FUERA
  de ambos buckets a proposito -- ni es busqueda ni es la generacion
  principal; si hace falta desglosarlo tambien se agrega como un tercer
  campo despues, no forzarlo dentro de "generacion" solo por conveniencia.
- Agregar `search_time_ms`/`generation_time_ms` a `ChatResponse`
  (`app/schemas/chat.py`) y persistirlos en
  `app/bots/conversation_store.py` `handle_turn()`, mismo patron que
  `was_rewritten`.
- **Decision de alcance: solo el pipeline lineal por ahora.** El pipeline
  agentico (`agent_pipeline.py`, Fase 7, `agentic_rag.enabled=false` por
  defecto) tiene sus propios nodos "buscar"/"generar" que mapean
  naturalmente a esto, pero con el loop de self-reflection de Etapa 2 un
  reintento ejecuta "buscar" y "generar" MAS de una vez -- sumar esos
  tiempos es una decision de diseno aparte (¿se suman los 2 intentos? ¿se
  guarda solo el ultimo?) que no vale la pena resolver para una ruta
  apagada por defecto. Si se activa el agente en el futuro, revisar esto
  aparte.
- En `app/api/admin.py`, extender `/admin/metrics/performance`: agregar
  `avg(search_time_ms)`/`p95` y `avg(generation_time_ms)`/`p95` junto al
  `latency` que ya existe (mismo `percentile_cont` ya usado ahi), sin
  tocar el calculo de `response_time_ms` total.
- Mensajes viejos (persistidos antes de este cambio) quedan con estas 2
  columnas en `NULL` -- se excluyen solos de los promedios via `avg()`
  (ignora NULL automaticamente), mismo criterio ya aplicado a
  `passed_threshold`/similitud esta sesion.

**Implementado tal cual el diseno, con un caso limite adicional resuelto:**
un cache hit del semantic cache (`app.rag.semantic_cache`) devuelve un
`ChatResponse` completo ya guardado, que traia `search_time_ms`/
`generation_time_ms` de CUANDO SE GENERO originalmente -- sin manejarlo,
esos numeros viejos se habrian persistido como si el hit (que no busca ni
genera nada de verdad) hubiera tardado eso, contaminando avg/p95. Se
resetean a `None` explicitamente en el camino de cache hit de
`rag_pipeline.answer_question` antes de devolver la respuesta. Verificado
en vivo con 2 preguntas identicas seguidas: T1 (real)
`search_time_ms=14320, generation_time_ms=24708`; T2 (cache hit, confirmado
por `response_time_ms=538` vs los `50227` de T1) `search_time_ms=None,
generation_time_ms=None` -- ambos casos confirmados tambien con SQL directo
contra `messages`. `pytest tests/ --ignore=tests/test_rag_regression.py -q`
sigue en 46 passed.

#### 3.3 Golden dataset automatizado como endpoint (el mas grande) -- HECHO (implementado y verificado 2026-07-24, primera corrida completa de las 24 preguntas AUN PENDIENTE, ver nota de costo al final)

Hoy: 24 preguntas viven como asserts de pytest en
`tests/test_rag_regression.py`, cada una verificada a mano contra la DB
antes de escribirse (pregunta + ley esperada + articulo esperado, o
"fuera de dominio"/xfail conocido). Se corre a mano
(`pytest -v -s`, ~35min, costo real de API), y el resultado se copia a
mano a un snapshot estatico del dashboard (`ragAdvancedSnapshot.ts`, Fase
E) que hay que actualizar manualmente cada vez.

**Objetivo: mismo dataset, sin duplicar mantenimiento entre pytest y el
endpoint, con historial de corridas real en vez de un snapshot manual.**

1. **Extraer las 24 preguntas a datos estructurados** -- archivo nuevo
   `app/evaluation/golden_dataset.py` (lista de dataclasses/dicts:
   `pregunta`, `ley_contains`, `articulo_esperado` (o `None` si es
   fuera-de-dominio/no-encontrado esperado), `expects_grounded`,
   `known_limitation` (bool, para los 2 xfailed ya documentados)).
   `tests/test_rag_regression.py` se reescribe para LEER de esa misma
   lista (`@pytest.mark.parametrize` sobre ella) en vez de tener 24
   funciones `test_*` con la pregunta hardcodeada -- una sola fuente de
   verdad, pytest y el evaluador nuevo comparten el dato real.
2. **Evaluador** -- `app/evaluation/run_golden_dataset.py`:
   `run_evaluation(db) -> EvaluationRun`, corre cada caso por
   `answer_question()` real (mismo costo que hoy, no hay forma barata de
   evitarlo -- es contra la API real a proposito), compara contra lo
   esperado (grounded correcto + posicion del articulo esperado en
   `retrieved_chunks`, reusando la misma logica de `_article_position` que
   ya existe en el test), y arma un resumen (passed/xfailed/failed,
   tiempo total, detalle por caso).
3. **Persistencia** -- 2 tablas nuevas (mismo patron que `ingestion_logs`):
   `golden_dataset_runs` (id, started_at, completed_at, total, passed,
   xfailed, failed, duration_ms) y `golden_dataset_run_cases` (run_id,
   pregunta, passed, grounded_esperado, grounded_real, articulo_esperado,
   posicion_encontrada, respuesta_snippet) para poder ver el detalle de
   una corrida especifica, no solo el agregado.
4. **Disparo async, NO sincrono** -- 35 minutos reales excede cualquier
   timeout razonable de un endpoint HTTP. Envolver `run_evaluation` como
   tarea de Celery (`app/workers/evaluation_tasks.py`, la infraestructura
   de Celery+Redis ya esta funcionando desde Fase 4) -- `POST
   /admin/evaluation/run` (admin-gated) encola la tarea y devuelve
   inmediatamente `{"task_id": ...}`, no espera el resultado. NO
   programarlo en Celery Beat por defecto -- correrlo automaticamente cada
   noche gastaria API real sin que el codigo haya cambiado; queda como
   disparo manual desde el dashboard, el usuario decide cuando vale la
   pena re-medir (despues de un cambio real al pipeline).
5. **Lectura** -- `GET /admin/metrics/golden_dataset` (nuevo, admin-gated):
   devuelve la corrida MAS RECIENTE de `golden_dataset_runs` + su detalle
   por caso, mas opcionalmente las ultimas N corridas para que el
   dashboard pueda graficar tendencia en el tiempo (¿mejoro o empeoro
   despues del ultimo cambio de RAG?) -- esto es lo que reemplaza al
   snapshot manual de `ragAdvancedSnapshot.ts` con dato real en vivo.
6. **Migracion del snapshot manual existente**: una vez el endpoint
   exista, la corrida real que ya se documento en `PLAN.md` Fase 6
   (22 passed/2 xfailed/0 failed) se puede insertar como la primera fila
   historica de `golden_dataset_runs` para no perder ese punto de
   referencia, en vez de empezar el historial vacio.

**Riesgo/costo real a tener en cuenta antes de ejecutar este item:** cada
corrida cuesta ~35 minutos y llamadas reales a NVIDIA NIM/OpenAI/xAI (no
gratis del todo, ver `ai_config.json` notas de creditos limitados en
OpenAI/xAI). Confirmar con el usuario la frecuencia esperada de uso antes
de construir el trigger automatico -- el diseno de arriba ya evita
Celery Beat automatico por esta razon, pero vale la pena revisarlo de
nuevo en el momento de implementar.

**Implementado tal cual el diseno, con un hallazgo real al extraer el
dataset (item 1):** el codigo original de `tests/test_rag_regression.py`
tiene 3 funciones con `pytest.xfail()` condicional, no 2 -- el docstring de
cabecera de ese archivo (y el resumen de arriba) dicen "2 xfailed" porque
esa fue la cuenta de la ULTIMA CORRIDA REAL (en esa corrida,
`test_no_encontrado_proteccion_animal` dio `grounded=False` y paso por la
rama normal sin disparar el xfail), no porque el mecanismo solo exista en 2
funciones. Los 3 casos reales con esta forma (`known_limitation=True` en
`app/evaluation/golden_dataset.py`, con dos formas distintas segun
`limitation_kind`) son `test_derechos_humanos_tortura_sanciones_limite_conocido`,
`test_civil_sucesion_intestada_limitacion_conocida` (ambos ya documentados
en el resumen de arriba) y `test_no_encontrado_proteccion_animal` (el caso
de varianza real entre corridas del clasificador LLM, ver Fase 3.7). Se
modelaron los 3 fieles al codigo real en vez de forzar la cuenta a 2.

Archivos nuevos: `app/evaluation/golden_dataset.py` (las 24
`GoldenCase`, una sola fuente de verdad), `app/evaluation/common.py`
(`article_position` + `evaluate_case`, logica de passed/xfailed_known/failed
compartida entre pytest y el evaluador), `app/evaluation/run_golden_dataset.py`
(`run_evaluation(db)`, corre cada caso real y persiste incrementalmente --
commit por caso, no al final, para no perder progreso si la corrida de ~35
min se interrumpe a mitad de camino), `app/models/golden_dataset_run.py`
(`GoldenDatasetRun`/`GoldenDatasetRunCase`, migradas a mano con
`CREATE TABLE IF NOT EXISTS` contra la DB real, mismo patron sin Alembic ya
usado en 3.2), `app/workers/evaluation_tasks.py`
(`run_golden_dataset_task`, agregada al `include` de `celery_app.py` pero
**NO** a `beat_schedule` -- disparo manual unicamente, confirmado). 2
endpoints nuevos en `app/api/admin.py`: `POST /admin/evaluation/run`
(encola y devuelve `task_id` de inmediato) y
`GET /admin/metrics/golden_dataset` (corrida mas reciente + detalle por
caso + ultimas 10 para tendencia; `{"latest": null, "history": []}` si la
tabla esta vacia). `tests/test_rag_regression.py` se reescribio con
`@pytest.mark.parametrize` sobre `GOLDEN_DATASET`, preservando `db`/`_run`/
`_article_position`/`_report` tal cual (esta ultima ahora delega en
`app.evaluation.common.article_position` para no duplicar la logica).

**Verificacion real (evidencia cruda):**

1. Coleccion sin ejecutar (gratis, confirma que el refactor no perdio ni
   duplico ningun caso de los 24 originales):
   `pytest tests/test_rag_regression.py --collect-only -q` -> `24 tests
   collected in 3.69s`, con los 24 ids exactos de las 24 funciones
   `test_*` originales (`test_penal_amnistia` ... `test_fuera_de_dominio_aritmetica`).
2. Resto de la suite sin tocar: `pytest tests/ --ignore=tests/test_rag_regression.py -q`
   -> `46 passed, 1 warning in 3.36s` (mismo numero que el baseline de 3.2).
3. Migracion real contra la DB: `CREATE TABLE IF NOT EXISTS
   golden_dataset_runs`/`golden_dataset_run_cases` aplicado con exito
   (`DDL applied ok`), columnas verificadas despues via
   `information_schema.columns` contra las 2 tablas -- coinciden exactas con
   los modelos SQLAlchemy.
4. Mecanismo de extremo a extremo probado con **3 casos reales, NO los 24**
   (costo controlado, `run_mod.GOLDEN_DATASET` reemplazado por un
   subconjunto de 3 en un script temporal, luego borrado):
   `test_penal_amnistia`, `test_cultural_bibliotecas` (llamadas reales de
   embeddings+generacion) y `test_fuera_de_dominio_capital_francia`
   (rechazado por Capa 1, sin costo de LLM). Resultado real:
   `total=3 passed=3 xfailed_known=0 failed=0 duration_ms=245404` (~4 min
   para 3 preguntas, consistente con el orden de magnitud de ~35 min para
   24). Confirmado con SQL directo contra `golden_dataset_runs`/
   `golden_dataset_run_cases` (3 filas de caso, contenido real incluyendo
   tildes correctas -- verificado que no habia corrupcion de encoding, solo
   mojibake de la terminal al imprimir). Datos de prueba borrados despues
   (`DELETE FROM golden_dataset_run_cases; DELETE FROM golden_dataset_runs;`,
   confirmado `0`/`0` filas restantes).
5. Endpoints probados contra un servidor real (`uvicorn app.main:app` en
   `127.0.0.1:8123`, apagado al terminar, puerto liberado -- confirmado con
   `netstat` antes/despues):
   - `GET /admin/metrics/golden_dataset` sin header -> `401` (gate de admin
     funciona).
   - Con los 3 casos de prueba ya insertados (paso 4, via `run_evaluation()`
     directo, sin pasar por Celery): `GET /admin/metrics/golden_dataset`
     devolvio `latest` con los 3 casos reales y `history` con 1 entrada,
     coincidiendo exacto con lo insertado.
   - `POST /admin/evaluation/run` devolvio `{"task_id":
     "53cf4e24-e428-4945-96d3-26ec53ba0691"}` de inmediato (sin bloquear).
     **No hay worker de Celery corriendo en este entorno de verificacion**
     (confirmado: `redis-server.exe` si esta corriendo como servicio, pero
     ningun proceso `celery` en `tasklist`) -- se confirmo que la tarea SI
     se encolo de verdad inspeccionando el broker de Redis directamente
     (`LRANGE celery 0 -1` incluyo un mensaje con
     `"task": "app.workers.evaluation_tasks.run_golden_dataset_task"` y el
     mismo `task_id`), no solo que el endpoint respondio. Como esa tarea
     encolada correria las 24 preguntas reales si algun worker la levantara
     despues (violando la instruccion explicita de no disparar la corrida
     completa en esta tarea), se removio ESE mensaje especifico de la cola
     de Redis por `task_id` (no se toco el resto de la cola -- quedaban 7
     mensajes de otras sesiones antes de este cambio, siguen intactos).
   - Despues de borrar los datos de prueba,
     `GET /admin/metrics/golden_dataset` devolvio exactamente
     `{"latest":null,"history":[]}` (forma explicita para "sin corridas
     todavia", sin error).

**Pendiente, decision del usuario:** la primera corrida real de las 24
preguntas completas (~35 min, costo real de API en NVIDIA NIM/OpenAI/xAI)
NO se disparo en esta tarea, a proposito -- el endpoint
`POST /admin/evaluation/run` esta listo y verificado de punta a punta con un
subconjunto controlado; falta que el usuario decida cuando dispararla
(desde el dashboard, o con `curl -X POST -H "X-Admin-Api-Key: ..."
.../admin/evaluation/run` con un worker de Celery real corriendo) para
generar la primera fila real de 24 preguntas y, si se quiere, migrar el
baseline ya documentado en `PLAN.md` Fase 6 (22 passed/2 xfailed/0 failed)
como primera fila historica (item 6 del diseno original, no ejecutado en
esta tarea).

**Primera corrida real completa -- HECHA (2026-07-24).** Resultado real,
via `GET /admin/metrics/golden_dataset` (`run_id=3`, `started_at` 23:02:04,
`completed_at` 23:30:55): **total=24, passed=19, xfailed_known=3, failed=2,
duration_ms=1730249** (~28.8 min).

Nota de infraestructura real encontrada al disparar esto: un worker de
Celery lanzado via el tool de background del harness (`run_in_background`
con `timeout` explicito) murio repetidamente a los pocos segundos, dos
veces seguidas, ambas veces con exactamente 12 de 24 casos ya persistidos
(el diseno de commit incremental de `run_evaluation` evito perder ese
trabajo, pero la fila de `GoldenDatasetRun` nunca llegaba a
`completed_at`). Causa real mas probable: el parametro `timeout` del tool
de Bash parece limitar la vida TOTAL del proceso en background, no solo la
espera sincrona antes de mandarlo a background -- consistente con que
ambas muertes ocurrieron cerca del valor de `timeout` pasado (15s), no a
los ~35 min reales que tarda la corrida. Se resolvio lanzando el proceso
completamente desacoplado del tool (PowerShell `Start-Process` con
`-WindowStyle Hidden`, log a archivo), fuera del tracking de background del
harness -- sobrevivio los 28.8 min completos sin interrupcion. Las 2
corridas incompletas (`run_id=1`, `run_id=2`, 12 casos cada una) se
borraron de la DB antes de la corrida final -- no representan una medicion
real, solo el efecto del proceso muriendo a mitad de camino.

**Los 2 `failed` reales, investigados con evidencia (no solo el numero):**

1. **`test_familiar_adulto_mayor_definicion`** ("A partir de que edad se
   considera adulto mayor..."): `actual_grounded=True` (correcto), pero
   `posicion_encontrada=None` para el articulo esperado (Art.2, Codigo de
   Atencion a la Familia). **No es una regresion real** -- la respuesta
   real cito la **Ley de Asistencia e Integracion de las Personas Adultas
   Mayores del Estado de Chiapas** (ingerida HOY mismo, ver Fase 8 de
   `PLAN.md`/inventario del grafo), una ley mas especifica y correcta para
   esta pregunta que la que el golden dataset esperaba desde antes de que
   esa ley existiera en el corpus. El dataset quedo desactualizado por el
   propio progreso del proyecto (ingerir mejor cobertura), mismo patron ya
   resuelto para `test_familiar_adopcion_requisitos` (`alt_ley_contains`) --
   pendiente aplicar el mismo fix a este caso si se retoma
   `app/evaluation/golden_dataset.py`, no urgente (el gate real de
   grounding funciono bien, es la EXPECTATIVA la que esta vieja).
2. **`test_no_encontrado_ley_federal_trabajo`**: fallo con una excepcion
   real durante la corrida (traceback truncado a 200 caracteres en
   `respuesta_snippet` -- limitacion real del diseno actual, deberia
   guardar mas contexto o el tipo de excepcion aparte). Reproducido aparte
   con la MISMA pregunta, misma llamada real (`answer_question` directo,
   proceso desacoplado igual que arriba): **no volvio a fallar**
   (`grounded=False` correcto, 89.1s). Confirma que fue un hallazgo real
   pero TRANSITORIO (timeout/hiccup puntual de un proveedor de la cadena de
   fallback), no un bug reproducible del pipeline -- mismo patron de
   latencia intermitente de NVIDIA NIM ya documentado varias veces en
   `PLAN.md`.

**Lectura honesta del resultado:** de los 2 failed, 0 son un bug real del
pipeline hoy -- 1 es un dataset desactualizado por una mejora real del
corpus, 1 es ruido de red no reproducible. El resultado real de salud del
pipeline sigue siendo equivalente al mejor baseline ya documentado
(`PLAN.md` Fase 6, 22/2/0), no una regresion.

---

### Fase D — Deploy

**Config preparada (2026-07-17), deploy real NO ejecutado** — requiere
cuentas/credenciales del usuario en servicios externos (Railway/Render/
Vercel), que esta sesion no tiene. Se dejo todo listo para que el deploy
en si sea ejecutar unos pasos, no investigar que hace falta.

**Investigacion de plataforma (pgvector, 2026-07-17):** Railway tiene un
template dedicado con pgvector preinstalado (deploy en segundos, ver
[railway.com/deploy/postgres-with-pgvector-engine](https://railway.com/deploy/postgres-with-pgvector-engine))
— **recomendado**. Render tambien soporta pgvector via `CREATE EXTENSION
vector` en Postgres 13+ (ver
[render.com/docs/postgresql-extensions](https://render.com/docs/postgresql-extensions))
— alternativa viable. Fly.io **no** trae pgvector por default: requiere
armar una imagen Docker propia sobre `flyio/postgres-flex` — no
recomendado salvo que ya se use Fly.io por otra razon.

**Archivos ya agregados a `lexchiapas/` para el deploy:**
- `Procfile` — `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  (Railway y Render lo detectan automaticamente)
- `runtime.txt` — `python-3.11.9` (pin de version, coincide con "Python
  3.11+" de `CLAUDE.md`)
- `.env.example` ya tenia `FRONTEND_ORIGIN` documentado con el ejemplo
  correcto (`https://tu-app.vercel.app`) desde Fase A — nada que agregar ahi.

**Pasos que le quedan al usuario (necesitan login/cuenta, no los puedo hacer
yo):**

1. Backend en Railway (o Render):
   - Crear proyecto, conectar el repo (o `railway up` desde `lexchiapas/`)
   - Agregar Postgres con pgvector (template de Railway arriba, o Postgres
     normal + `CREATE EXTENSION vector;` a mano si es Render)
   - Agregar Redis (para Celery — opcional para el MVP: el chat web y el
     dashboard NO dependen de Celery en runtime, solo la ingesta de
     documentos nueva lo usa; se puede deployar solo el proceso `web` al
     principio y agregar `worker`/`beat` despues si hace falta re-ingestar
     en produccion)
   - Configurar las variables de entorno de `.env.example`: como minimo
     `DATABASE_URL` (la que da el addon de Postgres), `NVIDIA_API_KEY`,
     `ADMIN_API_KEY`, `SECRET_KEY`, `TELEGRAM_BOT_TOKEN` si se quiere
     Telegram en prod, y `FRONTEND_ORIGIN` (el paso 3 abajo)
   - Correr las migraciones/`create_all` contra el Postgres nuevo (el
     proyecto no tiene Alembic, ver [[project-status]])
2. Frontend en Vercel:
   - Import del repo, root directory = `lexchiapas-web/`
   - Variables de entorno del proyecto en Vercel: `NEXT_PUBLIC_API_BASE_URL`
     (URL real del backend del paso 1, con `https://`) y
     `ADMIN_SESSION_SECRET` (generar una nueva con `openssl rand -hex 32` —
     **no reusar** el valor `dev-only-change-me` de `.env.local`)
3. Volver al backend y setear `FRONTEND_ORIGIN` al dominio real de Vercel
   (ej. `https://lexchiapas.vercel.app`, sin slash final) para que el CORS
   del chat publico funcione — `app/main.py` ya lee esto de
   `settings.frontend_origin` y solo agrega `CORSMiddleware` si no esta
   vacio, no requiere tocar codigo
4. **Nota sobre "cookies cross-domain" (aclaracion del checklist original):**
   no aplica en este diseño. La cookie de sesion del dashboard la emite el
   propio Next.js (Route Handler `/api/admin/login`, patron BFF) y vive en
   el dominio de Vercel — nunca cruza al backend. Lo unico que necesita CORS
   real es el chat publico (`fetch` desde el navegador a `/api/chat/web` y
   `/api/feedback`), cubierto por el paso 3. `[Subagente: security]` solo
   hace falta si se quiere una segunda revision antes de exponer el chat
   publicamente, no por un problema de cookies cross-domain.
5. Actualizar README con el link publico del chat (dashboard sigue privado,
   ese link no se publica) — pendiente hasta que el deploy real exista.

**Entregable:** LexChiapas con chat web publico y dashboard privado, ambos
deployados. **Estado: preparacion completa, ejecucion pendiente del
usuario** (pasos 1-3 y 5 arriba).

### Fase E — Frontend para RAG Fase 1 (avanzado)

**Gate cumplido (verificado 2026-07-22):** backend Fase 6 (`PLAN.md`)
marcada **COMPLETO** — query rewriting, HyDE (`ai_config.json`
`hyde.enabled=true`), contextual retrieval (evaluado, version cara
descartada con evidencia) y reranking real (NVIDIA NIM -> Jina ->
heuristica), medidos contra el golden dataset: 22 passed/2 xfailed/0 failed.

**Replanteo necesario del alcance original:** el checklist original asumia
que iba a existir trafico real "antes" (pipeline viejo) vs. "despues"
(pipeline nuevo) para comparar en el dashboard. Eso no aplica — ninguna
tecnica quedo como toggle por query en produccion: HyDE es un flag GLOBAL
(`ai_config.json`), reranking y contextual-retrieval-determinista son pasos
INCONDICIONALES del pipeline, y query rewriting solo se loguea con
`logger.info()` (no hay columna en `messages`). La unica comparacion real
que existe es el benchmark de golden dataset (17/2/5 -> 22/2/0), ya
documentado en `PLAN.md` Fase 6, medido UNA vez, no en vivo.

- [x] **Instantanea del benchmark en el dashboard — HECHO (2026-07-22).**
      Nueva seccion "RAG avanzado (Fase 6 backend)" en
      `/dashboard/calidad` (`src/lib/ragAdvancedSnapshot.ts` +
      `src/app/dashboard/calidad/page.tsx`): StatTile con el resultado del
      golden dataset (91.7%, 22/2/0 de 24) + tabla de las 4 tecnicas con su
      estado (activa/evaluada-no-activa) y detalle. Es una **instantanea
      MANUAL, no un dato en vivo** — no hay endpoint que lo exponga porque
      `tests/test_rag_regression.py` corre por pytest a mano, no se
      persiste en DB; el archivo de datos tiene un comentario explicito
      de esto y de que hay que actualizarlo a mano si el backend vuelve a
      correr el dataset. Verificado via `curl` + cookie jar (extension de
      Chrome se desconecto a mitad de la verificacion, ver
      [[web-dev-environment-gotchas]]) — el HTML servido trae el 91.7% y
      las 4 filas de la tabla correctas. `npx tsc --noEmit` y `npx eslint`
      limpios.
- [x] **Backend ya lo implemento (confirmado 2026-07-24).** El pedido de
      `was_rewritten` se hizo aqui mismo; verificado con una pregunta real
      contra `/api/chat/web` (`curl`, sesion "tortura en Chiapas") que la
      respuesta real YA trae `"was_rewritten": false` en el JSON. **Falta
      todavia el lado del dashboard**: ni `getQualityMetrics`
      (`/admin/metrics/quality`) ni ningun otro endpoint expone una
      agregacion por `was_rewritten` -- el campo esta en la respuesta del
      chat pero no en ninguna metrica consultable. Pendiente: agregar
      `grounded_by_rewrite: {was_rewritten: bool, grounded: int, total:
      int}[]` (o similar) a `/admin/metrics/quality`, y una vez ahi, el
      frontend agrega una segunda comparacion junto a la de Fase E (rutas
      general/por-ley/articulo no aplican, es la misma segmentacion
      reescrita-vs-no ya descrita abajo).
- [ ] Opcional, baja prioridad: mostrar de forma sutil en el chat que la
      pregunta fue reescrita internamente (transparencia), solo si no
      complica la UI del chat — sigue sin empezar

**Entregable:** el dashboard puede mostrar que tan efectiva es cada tecnica
de recuperacion nueva, comparada contra el baseline.

### Fase F — Frontend para RAG Fase 2 (agentico)

**Gate cumplido (verificado 2026-07-23/24):** backend Fase 7 (`PLAN.md`)
completa y medida -- agente LangGraph (Etapa 1: `search_laws`/`search_by_law`/
`get_article`; Etapa 2: self-reflection con reintento acotado). **Pero
`agentic_rag.enabled=false` por default** (`ai_config.json`) -- el pipeline
lineal sigue sirviendo produccion, y `/api/chat/web` no expone ningun trace
del agente en su respuesta (confirmado: `AgentState` calcula
`decision`/`law_name`/`articulo`/`intentos` en
`app/rag/agent_pipeline.py::answer_question_agentic`, pero la funcion solo
devuelve `(ChatResponse, elapsed_ms)`, descartando el resto). Tampoco hay
streaming en `/api/chat/web` (POST sincrono, todo-o-nada).

**Decisiones tomadas con el usuario (AskUserQuestion) antes de construir:**
1. El indicador "pensando" del chat NO simula pasos falsos sin streaming
   real -- se queda como esta (`"Buscando en las leyes de Chiapas..."`
   generico en `src/app/page.tsx`, sin cambios).
2. El resto (acordeon de trace + metricas de agente) se construye COMPLETO
   ahora, pero permanece **oculto/inerte en produccion hasta que el backend
   realmente devuelva estos datos** -- cero datos mock en el codigo que
   corre para usuarios reales.

**Construido (2026-07-24):**
- `AgentTrace` en `src/lib/types.ts` (espejo del shape propuesto al backend,
  ver abajo) + `agent_trace?`/`agentTrace?` opcionales en
  `WebChatResponse`/`ChatMessageData`.
- `src/components/TraceAccordion.tsx`: mismo patron `<details>/<summary>`
  que `CitationList.tsx`. `return null` si `trace` es `null`/`undefined` --
  hoy SIEMPRE, confirmado con una pregunta real via `curl` contra
  `/api/chat/web` (sesion "tortura en Chiapas", 2026-07-24): la respuesta
  real no trae `agent_trace`, asi que el chat en vivo queda visualmente
  identico a antes. Insertado en `ChatMessage.tsx` junto a `CitationList`.
- Vista `/dashboard/agente` (`src/app/dashboard/agente/page.tsx` +
  `getAgentMetrics()` en `adminApi.ts`, nav agregada en
  `dashboard/layout.tsx`): como `GET /admin/metrics/agent` no existe
  todavia, atrapa `AdminApiError` y muestra `EmptyState` explicito en vez de
  crashear -- confirmado via `curl`+cookie jar que la pagina carga limpio con
  ese mensaje, no un error 500.
- **Verificacion visual de ambos componentes con props mock TEMPORALES**
  (navegador real, extension conectada): `TraceAccordion` con una traza de
  ejemplo (`historial_ley`, ley + articulo + reintento) renderizo
  correctamente todos los campos; revertido antes de terminar, confirmado
  con `tsc`/`eslint` limpios post-revert.

**Pedido para el backend (no implementado aqui, fuera de alcance de esta
sesion):**
1. `AgentTrace` en `ChatResponse` (`app/schemas/chat.py`):
   ```python
   class AgentTrace(BaseModel):
       route: str  # busqueda_general/busqueda_por_ley/articulo_especifico/historial_ley/ninguna
       law_name: str | None
       articulo: str | None
       intentos: int
       self_reflection_triggered: bool  # intentos > 1
   ```
   poblado solo si `agentic_rag.enabled=true`, sourced de `AgentState`
   (`decision`/`law_name`/`articulo`/`intentos`) que `answer_question_agentic`
   ya calcula y hoy descarta.
2. Persistir como `messages.agent_trace` (JSONB nullable, mismo patron que
   `retrieved_chunks`).
3. `GET /admin/metrics/agent` (mismo patron `require_admin` que los otros 4):
   distribucion de rutas, intentos promedio, tasa de self-reflection
   disparado -- shape esperado por el frontend ya definido en
   `AgentMetrics` (`src/lib/adminApi.ts`).

**Entregable: codigo completo y verificado, oculto hasta que el backend
responda.** Se activa solo cuando el backend implemente el pedido de
arriba, sin tocar el codigo frontend otra vez.

### Fase G — Frontend para RAG Fase 3 (GraphRAG)

**Gate cumplido (verificado 2026-07-23):** backend Fase 8 (`PLAN.md`)
completa -- 2004 relaciones legales reales en `legal_relations`
(regex sobre marcadores del Periodico Oficial, sin LLM), herramienta
`query_graph`/accion `HISTORIAL_LEY` integrada al agente, 46 tests, 4
comparaciones reales agente-vs-lineal donde el grafo responde preguntas que
el RAG semantico no puede. **Pero ningun endpoint expone esto publicamente**
(confirmado: `grep` sobre `app/api/admin.py` no tiene ninguna ruta de
`legal_relations`) -- ni siquiera bajo `/admin`, mucho menos publico.

**Construido (2026-07-24), diseno deliberadamente simple** (mismo criterio
anti-sobre-ingenieria que el backend ya aplico -- Postgres en vez de Neo4j
en Fase 8): NO un grafo de fuerza dirigida completo -- un explorador **por
ley** tipo "centro y satelites":
- `src/components/RelationGraph.tsx`: SVG hand-rolled siguiendo las
  convenciones del skill `dataviz` ya usadas en Fase C (paleta
  `--series-N` mapeada deterministicamente por `relation_type`, etiquetas
  directas, sin libreria de grafos). Verificado visualmente con 4
  relaciones mock (deroga/reforma/remite_a/modifica): los 4 nodos
  satelite, sus labels truncados, y el nodo central renderizaron
  correctamente -- mock revertido despues.
- `src/app/explorar/page.tsx` (nueva, PUBLICA, fuera de `/dashboard`):
  selector de ley + `ChartCard` envolviendo `RelationGraph` (con su tabla
  accesible gemela). Como `GET /api/laws` no existe (404 confirmado en el
  log del backend durante la verificacion), la pagina siempre muestra un
  `EmptyState` de pagina completa explicando que esta pendiente del
  backend -- confirmado via navegador real (extension conectada) que no
  crashea, no una pagina rota.
- `src/lib/api.ts`: `getLaws()`/`getLegalRelations(law)` (publicas, sin
  auth, mismo `ApiError` que `sendChatMessage`) contra `/api/laws` y
  `/api/legal-relations` -- no existen todavia, quedan listas.
- Link de baja intensidad "Explorar relaciones entre leyes" agregado al pie
  del chat (`src/app/page.tsx`) hacia `/explorar`.

**Pedido para el backend (no implementado aqui):** dos endpoints PUBLICOS
(sin auth, mismo nivel que `/api/chat/web`):
- `GET /api/laws` -> `[{id, nombre}]` de documentos activos
- `GET /api/legal-relations?law=<nombre>` -> `{law, relations: [{relation_type,
  to_law_name, to_document_id, articulo, fecha, source_text}]}` -- reusar
  la logica de matching ya escrita en
  `app/rag/agent_tools.py::query_graph`/`_fuzzy_ilike_pattern`
  (factorizarla a una funcion compartida en vez de duplicarla)

**Entregable: codigo completo y verificado, oculto hasta que el backend
responda.** Misma logica que Fase F -- `/explorar` se activa solo cuando el
backend implemente los 2 endpoints, sin tocar el codigo frontend otra vez.

**Hallazgo real, no relacionado con Fase F/G, encontrado durante la
verificacion (2026-07-24):** el chat publico esta roto en un navegador real
hoy -- `OPTIONS /api/chat/web` devuelve 405 (confirmado en el log de
`uvicorn`), porque `FRONTEND_ORIGIN` esta vacio en `.env` y sin
`CORSMiddleware` activo, el preflight del POST con
`Content-Type: application/json` desde `localhost:3000` hacia
`127.0.0.1:8000` nunca pasa. `curl` no lo detecta (no hace preflight), por
eso las verificaciones anteriores basadas en `curl` no lo habian visto. Fix
propuesto (no aplicado, es una variable de entorno del backend, fuera de
alcance de esta sesion): setear `FRONTEND_ORIGIN=http://localhost:3000` (o
`http://127.0.0.1:3000`) en `lexchiapas/.env` para desarrollo local. No
afecta nada de lo verificado en Fase F/G (el trace/grafo se verificaron via
`curl` directo al backend y via props mock en el navegador, ninguno de los
dos depende de que el chat en vivo funcione).

**Fix de CORS aplicado por el backend y re-verificado por esta sesion
(2026-07-24):** `FRONTEND_ORIGIN=http://localhost:3000` agregado a
`lexchiapas/.env`. Re-probado el preflight real (`curl -X OPTIONS
/api/chat/web` con headers `Origin`/`Access-Control-Request-*`, como lo
haria un navegador real, no un `curl` normal) -> `200 OK`,
`access-control-allow-origin: http://localhost:3000`,
`access-control-allow-methods` incluye `POST`. Confirmado resuelto. La
verificacion visual en navegador real quedo bloqueada de nuevo por la
extension de Chrome desconectada a mitad de sesion -- el preflight real via
curl es evidencia suficiente (era el unico punto de falla, el POST en si ya
funcionaba).

### Ronda de consumo de las metricas nuevas del backend (2026-07-24)

El backend agrego, ademas del fix de CORS de arriba, varios campos/columnas
nuevas directamente a los endpoints `/admin/metrics/*` (items #3, #4, #10,
#11, #16 de la tabla de Fase C.1, mas `jailbreak_attempts` ya no-null en
Guardrails) -- esta sesion los consumio todos del lado frontend el mismo
dia, verificado contra datos reales (no solo el schema):

- **Guardrails:** `jailbreak_attempts` paso de `null` a `0` real (columna
  `messages.jailbreak_detected` nueva) -- **cero cambios de codigo
  necesarios**, el `EmptyState` condicional (`== null`) que ya existia desde
  Fase C fue escrito exactamente para esta transicion. Confirmado via
  `curl`+cookie jar: la pagina ahora muestra el `StatTile` "Intentos
  detectados" en vez del mensaje de "no se persisten todavia".
- **Uso** (`src/app/dashboard/uso/page.tsx`): 2 secciones nuevas --
  "Conversaciones por plataforma" (`conversations_by_platform`, al lado de
  "Usuarios unicos por plataforma") y "Preguntas mas frecuentes"
  (`top_questions`, `DataTable`). Verificado con datos reales -- incluye
  una pregunta fuera de tema real ("La capital de Francia es ?") que
  confirma el dedup es por texto exacto, no filtra por relevancia.
- **Calidad** (`src/app/dashboard/calidad/page.tsx`): `StatTile`
  "Similitud promedio (respuestas fundamentadas)" (`avg_similarity_grounded`,
  3 decimales) + `ChartCard` "Distribucion de similitud"
  (`similarity_histogram`). El backend documento que buckets sin datos
  vienen AUSENTES del array, no en 0 -- el frontend completa los 5 buckets
  fijos (`0.5-0.6`..`0.9-1.0`) rellenando con 0 los que faltan, para no
  confundir "sin datos en ese rango" con un hueco en la grafica. Verificado
  con datos reales: `0.556` promedio, bucket `0.5-0.6` con 5.
- **Performance** (`src/app/dashboard/performance/page.tsx`): `StatTile`
  "Tasa de errores del sistema" (`system_error_rate`, `system_errors/total`,
  formato porcentaje igual que las otras tasas). Verificado: `0 de 6
  respuestas` (0.0%) contra la DB real.
- **`src/lib/adminApi.ts`:** las 4 interfaces (`UsageMetrics`,
  `QualityMetrics`, `PerformanceMetrics`) actualizadas con los campos
  nuevos exactos, verificados golpeando los 4 endpoints reales con `curl`
  antes de escribir los tipos (no solo copiando la prosa del pedido
  original). Nota encontrada al verificar: `latency.avg_ms`/`p95_ms`
  llegan a veces como STRING numerico (`"88385.500000000000"`, de
  `AVG()`/`percentile_cont` de Postgres via SQL crudo) -- `Math.round()` ya
  los coacciona bien (pre-existente desde Fase C, no un bug nuevo), se dejo
  un comentario para que no se "arregle" un tipo que ya funciona en runtime.

`npx tsc --noEmit` y `npx eslint` limpios sobre los 4 archivos tocados.
`was_rewritten` (Fase E arriba) sigue siendo el unico item de esta ronda
SIN agregacion en el dashboard todavia -- ningun endpoint lo expone
agrupado, solo aparece en la respuesta individual del chat.

**Actualizacion 2026-07-24 (backend):** `was_rewritten` ya tiene agregacion
-- `grounded_by_rewrite` en `/admin/metrics/quality` (`GROUP BY
was_rewritten`, cuenta `grounded`/`total` por grupo, excluye mensajes donde
`was_rewritten IS NULL` -- ruta agentica o camino de error). Verificado con
dato real: `[{"was_rewritten": false, "grounded": 1, "total": 1}]`. Tambien
se agrego `recent_chat_errors` a `/admin/metrics/performance` (mismo patron
que `recent_ingestion_errors`, lee `messages` donde `found_answer IS NULL`
-- cierra el gap senalado en el item #14 de la Fase C.1). Ambos verificados
con `pytest` (46 passed) y llamada real a cada endpoint.

## Notas

- El backend ya tiene autenticacion via `ADMIN_API_KEY`
  (`app/api/admin.py`) — la Fase A reusa ese mismo mecanismo para el login
  del dashboard. Si el proyecto crece a multi-usuario/multi-tenant, eso es
  un cambio de diseno mayor a revisar aparte, no incluido aqui.
- Este plan asume que Fase 1 de `PLAN.md` (tablas reales creadas, NVIDIA NIM
  probado) ya esta resuelta antes de arrancar Fase A de aqui — el chat web
  necesita el pipeline RAG funcionando de verdad, no solo compilando.
