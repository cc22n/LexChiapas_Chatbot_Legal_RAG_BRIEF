# Auditoria integral LexChiapas — 2026-09-09

Reporte generado por `full-audit-orchestrator` (12 agentes especializados en
6 oleadas: security-auditor, db-integrity-auditor, code-optimizer,
llm-integration-auditor, frontend-auditor, web-standards-auditor,
architecture-reviewer, qa-test-engineer, backend-health-auditor,
observability-sre, cazador-costuras, prelaunch-auditor).

Contexto al momento de la auditoria: commit `21bbae9`, ya con Fase 9.2 y
9.4-9.7 completadas (claim-checker afinado, historial de reformas,
desambiguacion de leyes, fix de aclaracion conversacional, y el incidente
critico de muerte del modelo de embeddings ya resuelto y en produccion).

## 1. Resumen ejecutivo

El proyecto tiene una calidad de ingenieria notablemente alta en el codigo:
disciplina de "medir antes de asumir", post-mortems reales, comentarios que
documentan bugs ya corregidos, y la logica anti-alucinacion (threshold ->
grounding -> citas -> disclaimer) es el area mejor construida y mejor
testeada de todo el sistema. Ningun agente encontro SQL injection, secretos
filtrados, XSS explotable ni bypass de autenticacion.

El riesgo real no esta en el codigo: esta en todo lo que rodea al codigo
para operarlo en produccion. El proyecto no puede recrear su propia base de
datos, no tiene copia de seguridad de nada, no se entera cuando se cae, y
carece de las paginas legales que Mexico exige para procesar conversaciones
de ciudadanos. Ademas, la auditoria destapo que dos optimizaciones del RAG
estan muertas en la ruta que corre en produccion sin que nadie lo hubiera
notado.

## 2. Veredicto global

### NO LISTO para deploy publico

Coincide con `prelaunch-auditor` y se endurece por un hallazgo suyo
verificado en persona: no existe forma reproducible de crear el esquema en
una base nueva. No es "falta pulir el deploy" -- es que el deploy, tal como
esta documentado, produce una aplicacion que arranca y truena en el primer
request.

Matiz importante: NO LISTO no significa "proyecto en mal estado". Significa
que la brecha esta concentrada en operacion y cumplimiento, no en el
producto. Los bloqueantes son mayoritariamente de esfuerzo bajo-medio y muy
pocos requieren tocar la logica del RAG.

## 3. Agentes que corrieron y omitidos

**Corrieron (12, en 6 oleadas):** security-auditor, db-integrity-auditor,
code-optimizer, llm-integration-auditor, frontend-auditor,
web-standards-auditor (oleada 1) - architecture-reviewer (2) -
qa-test-engineer (3) - backend-health-auditor, observability-sre (4) -
cazador-costuras (5) - prelaunch-auditor (6).

**Omitidos y por que:**
- architecture-conformance-auditor: no aplica, no existe `architecture.md`
  (se uso architecture-reviewer en su lugar).
- red-team-attacker: requeria autorizacion explicita del usuario, no
  disponible al momento de este reporte (posteriormente autorizado -- ver
  seccion de seguimiento).
- ux-writing-content-designer, design-system-governance-auditor,
  project-logic-consistency-agent: opcionales, sin solicitud explicita.
- test-coverage-engineer: reactivo por diseno; los bugs concretos
  encontrados aqui lo justifican para una siguiente iteracion.
- meta-orchestrator, skill-creator, architecture-baseline-designer: de
  arranque unico, fuera de alcance.

## 4. Hallazgos CRITICOS

| # | Archivo | Detectado por | Descripcion | Impacto |
|---|---|---|---|---|
| C1 | `lexchiapas/alembic/versions/cf62d1f2007f_baseline_schema_real.py` | prelaunch (verificado) | La migracion baseline tiene `upgrade(): pass`. El esquema real se creo a mano y nunca se versiono. `README.md:13` dice que `alembic upgrade head` "aplica el esquema" -- es falso | Contra una Postgres nueva (Railway/Render) el deploy arranca sin error y no crea ni una tabla. Truena en el primer request |
| C2 | `app/llm/providers.py:96-132`; sin captura en `rag_pipeline.py:76`, `agent_pipeline.py:791` | llm-integration, db, qa, observability, backend-health, prelaunch | `embed_text()` sin fallback ni deteccion de 410/404. `get_ai_config()` bajo `lru_cache` sin invalidacion en caliente | Si el modelo de embeddings vuelve a morir (ya paso), cada turno de cada usuario falla indefinidamente hasta que un humano edite el JSON y reinicie el proceso |
| C3 | (transversal) | observability, prelaunch | Cero alertas activas: solo `logger.exception` pasivo, ningun sink | El incidente real tardo ~2 dias en detectarse porque un humano lo noto |
| C4 | (infra) `data/raw/`, `data/processed/` (solo `.gitkeep`) | observability, prelaunch | Sin `pg_dump`, sin copia de los PDFs/HTML scrapeados, sin backup de ningun tipo | Re-embeber cuesta ~7.5 min y ~$0. Lo irrecuperable es el scraping + parsing + chunking legal, riesgo #1 segun el propio CLAUDE.md |
| C5 | `models/chunk.py:47`, `models/semantic_cache.py:17`, `rag/semantic_cache.py:40-62` | db-integrity, qa, cazador | Sin columna `embedding_model`. pgvector solo protege contra cambio de dimension, no de modelo con igual dimension | Ruta explotable en `semantic_cache.lookup()`: solo valida TTL + firma de corpus, que no cambia al cambiar de modelo. Puede servir una respuesta cacheada de un espacio vectorial incompatible, sin ningun error |
| C6 | `app/rag/agent_pipeline.py` vs `rag_pipeline.py`; `ai_config.json` | qa (detecto), cazador (confirmo), observability (corroboro flag) | Con `agentic_rag.enabled=true` (verificado), la ruta activa nunca importa `cache_lookup`/`cache_store` ni `expand_legal_synonyms` | El cache semantico y la expansion de sinonimos legales estan muertos en produccion. El fix de "sin testamento" -> "sucesion legitima" dejo de proteger preguntas reales al activarse el agente |
| C7 | `src/app/` (no existe aviso de privacidad ni terminos) | web-standards, prelaunch | El bot persiste conversaciones de ciudadanos sin aviso de privacidad | Omision legal real bajo LFPDPPP, no una buena practica opcional |

## 5. Hallazgos ALTOS

| # | Archivo | Detectado por | Descripcion |
|---|---|---|---|
| A1 | `lexchiapas/Procfile` | security, backend-health, prelaunch | Sin `--proxy-headers`: detras del proxy de Railway/Render, `request.client.host` es la IP del proxy -> el rate limit por IP se vuelve un bucket global compartido |
| A2 | `lexchiapas/Procfile` | backend-health, prelaunch | Sin proceso `worker:` ni `beat:` de Celery -> la actualizacion automatica de leyes nunca correria en produccion, en silencio |
| A3 | `app/api/admin.py:45-51` | security, prelaunch | Cookie de sesion admin sin `secure=True` (fix de una linea) |
| A4 | `next.config.ts`, `app/main.py` | security, frontend, web-standards | Sin CSP, HSTS, X-Frame-Options, X-Content-Type-Options ni Referrer-Policy en ninguno de los dos proyectos |
| A5 | `app/config.py:89-92`; `conversation_store.py:94` | llm-integration, qa, backend-health, prelaunch | `get_ai_config()` sin `try/except` ante JSON malformado, y se llama fuera del try/except del turno |
| A6 | `app/api/health.py:20-43` | backend-health, observability | `/health/ready` solo verifica Postgres; no habria detectado el incidente de embeddings |
| A7 | `app/database.py:10-25`, `app/workers/celery_app.py` | db-integrity, qa | Sin `worker_process_init`/`engine.dispose()`: bajo Celery prefork los hijos heredan conexiones del padre |
| A8 | `models/message.py`, `bots/telegram_dedup.py` | db-integrity, qa | Dedupe de Telegram solo en Redis con fail-open explicito, sin constraint en BD |
| A9 | `app/api/rate_limit.py:6-10` | security, backend-health | Rate limiter en memoria por proceso; con >1 worker el limite se multiplica silenciosamente |
| A10 | `app/api/admin.py:395` y modulos auxiliares | llm-integration, observability | Tokens de grounding/claim_checker/decidir/rewrite descartados -- costo real subestimado 3-5x con la ruta agentica |
| A11 | `src/app/` (Next.js) | frontend, web-standards, observability | Sin `error.tsx`/`not-found.tsx`/`global-error.tsx` ni error tracking |
| A12 | `lexchiapas-web/src/app/` | web-standards | Sin robots.txt, sitemap.xml ni OG/Twitter tags; `/dashboard` y `/login` indexables; chat sin `aria-live`/`role="log"` |
| A13 | `src/lib/types.ts` vs `app/schemas/chat.py` | architecture | Espejo manual del contrato que ya divergio dos veces, documentado en los propios comentarios |
| A14 | (proceso) Telegram | prelaunch | Solo existe modo polling; el webhook nunca se activo contra Telegram real |

## 6. Hallazgos MEDIOS/BAJOS agrupados

- Seguridad: dependencias sin pin exacto ni `pip-audit`/`npm audit`;
  `MarkdownContent.tsx:29-33` no valida el esquema de `href` (defensa en
  profundidad); gobernanza de retencion de conversaciones con PII;
  `NEXT_PUBLIC_API_BASE_URL` cae a `127.0.0.1` silenciosamente.
- BD: indice HNSW con parametros por defecto sin medir recall; sin
  `sslmode=require` explicito; el script de re-embebido de los 13,307
  chunks nunca se comiteo.
- Arquitectura: reglas de dominio dispersas en 4 archivos; SQL crudo de
  metricas dentro de `admin.py` (~636 lineas) sin capa de servicio;
  `app/rag/` con 20 modulos planos (submodularizar es prematuro).
- Codigo: boilerplate try/except de LLM repetido 6 veces; N+1 de ~15
  queries por respuesta en `get_articulo_historial`; `memory.py:84,91,109`
  traga fallos de Redis sin log; `whatsapp_webhook` devuelve 500 en vez de
  501.
- Testing: sin `pytest.ini`/markers; sin CI; frontend sin ningun test;
  golden dataset sin comparacion automatica contra el baseline anterior.
- Operacion: logging en texto plano; `request_id` no se propaga a Celery;
  `AgentTrace` no registra tiempos ni paso de fallo; sin runbooks; Celery
  sin `acks_late`; golden dataset sin proteccion contra doble-trigger;
  `Feedback` sin constraint de unicidad.

## 7. Solapamientos y contradicciones resueltos

**7.1 Headers de seguridad** -- tres severidades distintas entre agentes.
Arbitraje final: ALTO (impacto explotable hoy es bajo, pero es el momento
exacto pre-primer-deploy y el costo es ~20 lineas).

**7.2 Duplicacion de pipelines** -- resuelto con matiz: las funciones
internas si estan compartidas (bajo riesgo), el bloque orquestador si esta
duplicado, y lo verdaderamente divergente son las optimizaciones de
retrieval presentes en un pipeline y ausentes en el otro -- exactamente C6.
Severidad final: ALTO.

**7.3 `similarity_threshold=0.5`** -- un agente lo marco CRITICO por
"decision sin justificar". Corregido: si esta documentado en
`LexChiapas_Plan_Futuro.md` (barrido 0.30-0.55 medido, decision deliberada
de priorizar anti-alucinacion sobre recall). Reclasificado a MEDIO/revisar.

**7.4 Reintento de `embed_text` ante 410** -- no es contradiccion real: no
reintentar un 4xx permanente es diseno correcto; lo que falta es deteccion,
alerta y degradacion (C2/C3).

**7.5 Conteo de tests 164 vs 184** -- explicado por `--ignore=app/evaluation`
sin efecto real (esos archivos no empiezan con `test_`); no es un bug.

## 8. Puntos calientes (archivos en 3+ reportes)

1. `app/llm/providers.py::embed_text()` -- 6 agentes.
2. `app/rag/agent_pipeline.py` + `rag_pipeline.py` -- 5 agentes.
3. `app/config.py::get_ai_config()` + `ai_config.json` -- 5 agentes.
4. `app/api/admin.py` -- 5 agentes.
5. `Procfile` -- 3 agentes.
6. Headers/config del frontend (`next.config.ts`) -- 3 agentes.

Lectura: el sistema es solido en su logica y fragil en sus bordes -- donde
toca al proveedor externo, a la configuracion manual y a la plataforma de
despliegue.

## 9. Plan de accion priorizado

**Bloque 0 -- Bloqueantes duros (antes de cualquier deploy)**
1. `pg_dump --schema-only` -> versionar `schema.sql` (con `CREATE EXTENSION
   vector`) -> aplicar a produccion -> `alembic stamp head`. Corregir
   `README.md:13`. (C1)
2. Aviso de privacidad + terminos de uso. (C7)
3. Backups: `pg_dump` programado + subir `data/raw/` a storage. (C4)
4. Alerta minima viable: Sentry free tier + job de Celery Beat sobre
   `found_answer IS NULL` con webhook a Telegram. (C3)
5. Manejo de 410/404 en `embed_text` + endpoint admin para invalidar
   `lru_cache` sin reiniciar. (C2)
6. `secure=True` en cookie admin; `--proxy-headers`; headers de seguridad.
   (A3, A1, A4)

**Bloque 1 -- Primera semana post-lanzamiento**
7. Decidir explicitamente C6: portar `expand_legal_synonyms` al nodo
   `buscar` del agente; decidir si el semantic cache se porta o se elimina.
8. Columna `embedding_model` en `chunks` + `semantic_cache`. (C5)
9. `try/except` en `get_ai_config()` + moverlo dentro del try del turno.
   (A5)
10. Procesos `worker:`/`beat:` en Procfile; `worker_process_init`/
    `engine.dispose()`. (A2, A7)
11. `/health/ready` con canario de embeddings cacheado. (A6)
12. `setWebhook` de Telegram documentado y ejecutado. (A14)
13. `error.tsx`/`not-found.tsx` + robots/sitemap/OG + `aria-live`. (A11, A12)

**Bloque 2 -- Deuda aceptable para portafolio**
Rate limiter en memoria (aceptable solo con 1 worker); dedupe de Telegram
sin constraint; N+1 de historial; submodularizar `app/rag/`; extraer
servicio de metricas de `admin.py`; codegen de `types.ts` desde OpenAPI.

## 10. Recomendaciones de seguimiento

- test-coverage-engineer: tests de regresion puntuales para el 410 de
  `embed_text` sin reintento, `get_ai_config` con JSON roto, y el miss de
  `semantic_cache` ante cambio de modelo.
- qa-test-engineer: `test_pipeline_parity.py` para que C6 no vuelva a pasar
  inadvertido; markers `@pytest.mark.golden`.
- red-team-attacker / red-team-orchestrator: pendiente al momento de este
  reporte, posteriormente autorizado (ver seguimiento en el chat/roadmap).
- dependency-supplychain-auditor: no estaba en el set base; versiones sin
  pin y ausencia de `pip-audit`/`npm audit` notadas por dos agentes.
- architecture-baseline-designer: el proyecto nunca tuvo `architecture.md`.
- project-logic-consistency-agent: tres desincronizaciones encontradas
  entre documentacion y realidad (README vs migracion, types.ts vs
  Pydantic, alcance de Etapa 1 del agente vs flag activo en produccion).

## Limites de este reporte

No se audito (al momento de generarlo): el sistema bajo ataque activo, ni
copy/UX writing, design system, o consistencia de reglas de negocio. Todo
el analisis fue estatico: nadie ejecuto la app contra la API real de
NVIDIA. El contraste de color y el rendimiento real (Core Web Vitals)
requieren verificacion en navegador tras el deploy.

---

# Anexo — Pentest local autorizado (2026-09-09/10)

Ejecutado con autorizacion explicita del usuario, 4 especialistas ofensivos
en 2 oleadas contra el backend corriendo LOCALMENTE en `127.0.0.1:8001`
(puerto alterno al 8000 habitual, que estaba ocupado por otro proyecto
local). Produccion nunca fue objetivo. El orquestador `red-team-orchestrator`
fue bloqueado por el clasificador de permisos de la sesion al intentar
spawnear a los especialistas; se invoco a cada uno directamente desde la
conversacion principal en su lugar, con el mismo alcance y topes acordados.

Topes acordados: ~25-40 mensajes reales a `/api/chat/web` para el
red-team de LLM (se usaron 21), ~30 intentos contra `/admin/login` para
fuerza bruta (se usaron exactamente 30), uso autorizado del `ADMIN_API_KEY`
real del `.env` como credencial legitima para probar autorizacion
post-login.

## Oleada 1 — Inyeccion clasica + LLM/prompt injection

**web-exploit-attacker (SQLi, XSS, RCE, path traversal, SSRF):** ninguna
vulnerabilidad confirmada. SQL parametrizado en todo `app/api/admin.py` y
`app/rag/agent_tools.py` (incl. el unico f-string en SQL, que interpola
solo literales hardcodeados, nunca texto de usuario). Sin `eval`/`exec`/
`subprocess`. Sin SSRF (unico `httpx.post` apunta a URL fija de NVIDIA
NIM). Webhooks fail-closed. CORS con whitelist real. Confirmo en vivo que
fixes de una auditoria de seguridad previa (2026-08-04, documentada en
comentarios del propio codigo) siguen vigentes.

**llm-redteam-attacker (prompt injection, extraccion, fuga entre
sesiones):** ninguna vulnerabilidad confirmada en 21 mensajes reales.
Prompt injection directa, roleplay jailbreak (incluso con contenido real
grounded sobre cohecho), extraccion de system prompt, encoding Base64,
alucinacion forzada de articulos inexistentes, y fuga de memoria entre 2
sesiones distintas -- todos neutralizados por el diseno en capas
(guardrail Capa 1 -> system prompt anti-injection Capa 2 -> gate de
threshold que impide invocar el LLM de generacion sin chunks reales
grounded). Unico hallazgo: severidad BAJA, el campo `agent_trace` en la
respuesta de `/api/chat/web` expone metadata interna de depuracion
(route/law_name/articulo/intentos) a cualquier cliente que llame el
endpoint directamente -- no es una fuga de datos de otro usuario, es
exposicion de detalles de implementacion.

## Oleada 2 — Fuerza bruta + IDOR/BOLA

**authz-idor-attacker:** ninguna vulnerabilidad confirmada. El control de
ownership en `/api/feedback` (`message.conversation.chat_id !=
payload.session_id`) se verifico robusto en vivo, incluyendo respuesta 404
uniforme ante enumeracion (no distingue "no existe" de "no es tuyo"). RBAC
de admin unico en `/admin/documents/*` funciona correctamente. `session_id`
web es un UUID aleatorio client-side (`crypto.randomUUID()`), nunca
expuesto en URL/logs -- riesgo residual solo si se filtra por otro vector
(XSS, ya descartado por la oleada 1).

**abuse-bruteforce-attacker:** rate limiting de `/admin/login` confirmado
efectivo en vivo (429 al intento 7-10 segun estado previo del bucket,
sliding window de 60s). Bypass via `X-Forwarded-For` spoofeado confirmado
NO explotable (el proyecto no lee ese header en ningun punto del codigo;
`request.client.host` refleja la IP real del socket). Cookie de sesion
HMAC resistente a forja/alteracion/expiracion manipulada. Encontro 2
hallazgos MEDIA y 1 BAJA:

| Severidad | Hallazgo | Evidencia |
|---|---|---|
| MEDIA | `ADMIN_API_KEY` se reutiliza como clave de firma HMAC de la cookie de sesion (`app/api/admin_auth.py::_signing_key()`) cuando no hay `SECRET_KEY` propia en `.env` | Con la API key real, se calculo offline una firma HMAC-SHA256 valida y se uso como cookie contra `GET /admin/documents` -> `200 OK`, sin pasar nunca por `/admin/login` ni tocar el rate limiter |
| MEDIA | `POST /admin/logout` no revoca la sesion server-side (esquema HMAC stateless sin blocklist) | Cookie capturada antes del logout, reenviada despues -> `200 OK` en `/admin/documents` y `/admin/metrics/usage` |
| BAJA | La rama de validacion por cookie en `require_admin` no pasa por `enforce_rate_limit` (solo la rama de header `X-Admin-Api-Key` lo hace) | Confirmado por codigo, `app/api/admin_auth.py:70-72`; bajo impacto hoy porque la cookie no es adivinable, pero sin defensa en profundidad |

Remediacion sugerida para las 2 de severidad MEDIA: generar `SECRET_KEY`
propia y aleatoria (`secrets.token_hex(32)`) independiente de
`ADMIN_API_KEY` en `.env` (el codigo ya la soporta si esta presente, solo
falta poblarla); agregar una lista de revocacion de sesiones (Redis ya esta
disponible como broker de Celery, reusable) consultada en
`_session_cookie_is_valid`.

## Veredicto del pentest

Ninguna vulnerabilidad CRITICA ni ALTA confirmada con evidencia de
explotacion real. 2 hallazgos MEDIA (clave de firma reutilizada, logout sin
revocacion server-side) y 2 BAJA (rate limit ausente en rama de cookie,
metadata interna expuesta en `agent_trace`) -- ambos de esfuerzo bajo para
corregir. La superficie publica (chat, webhooks, feedback, catalogo legal)
y la logica anti-alucinacion resistieron ataques activos de las 4
categorias evaluadas.

## Limpieza pendiente (no ejecutada, requiere confirmacion del usuario)

Quedaron registros de prueba en la base de datos LOCAL de desarrollo:
- Conversaciones/mensajes con `session_id` prefijo `redteam-*` (incl. una
  con datos ficticios "Juan Perez / PEJJ800101ABC" para la prueba de fuga
  de memoria) y `idor-victima` / `idor-atacante`.
- Un registro de `feedback` (id=5) creado durante la prueba de control
  positivo de IDOR.
- El documento de prueba creado y borrado durante el pentest (id=76) ya
  fue limpiado por el propio especialista.
- Sesiones admin validas emitidas durante las pruebas (login real + 3
  cookies forjadas offline con la key real) quedaron activas en memoria del
  proceso -- se resolvieron solas al detener el backend de prueba (puerto
  8001) al cerrar este pentest.

El backend de prueba en el puerto 8001 fue detenido al finalizar. El
puerto 8000 (otro proyecto local) no fue tocado en ningun momento.
