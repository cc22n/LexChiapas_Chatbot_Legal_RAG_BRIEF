# LexChiapas — Plan futuro (post Fase 8)

Con `PLAN.md` (Fases 0-8, backend) y `WEB_FRONTEND_PLAN.md` (Fases A-G, web)
completos en lo esencial, este documento junta dos cosas en un solo lugar:

**Nota de actualizacion (verificado via grafo de `graphify`, 2026-07-24):**
`WEB_FRONTEND_PLAN.md` crecio con las Fases E/F/G *despues* de que este
documento se escribiera (2026-07-23) — la Parte 1 de abajo ya incorpora esos
pedidos nuevos al backend. Ademas, 2 de los items que este documento marcaba
como "pendiente" en su primera version (persistir `jailbreak_attempts` y la
columna `was_rewritten`) ya se resolvieron del lado backend un dia despues
de escribirse — ver nota en cada fila correspondiente en la Parte 1.D en vez
de asumir que siguen pendientes.

1. **Inventario real** de todo lo que quedo mencionado como "opcion",
   "pendiente" o "diferido" en algun documento del proyecto — con su estado
   REAL verificado (implementado-pero-apagado / evaluado-y-rechazado /
   genuinamente sin empezar), no una relectura optimista.
2. **Propuesta de roadmap nuevo**, de bajo costo/alto valor, para cuando se
   retome trabajo aqui.

No duplica el detalle tecnico de cada item — cada fila enlaza a la seccion
del documento fuente donde esta la evidencia completa.

---

## Parte 1 — Inventario de lo ya documentado

### A. Implementado y funcionando, pero APAGADO por defecto (flag en `ai_config.json`)

Estos no son trabajo pendiente — el codigo existe, esta probado, y la
decision de dejarlos apagados fue explicita (mismo criterio en los 3: "no
asumir beneficio, medirlo con evidencia real primero"). Se reactivan
cambiando una linea en `ai_config.json`, sin tocar codigo.

| Item | Estado real | Por que sigue apagado | Para reactivar |
|---|---|---|---|
| `agentic_rag.enabled` | **CONFIRMADO tras el fix (2026-07-25): 21 passed / 2 xfailed_known / 1 failed** (24 preguntas completas, `answer_question_agentic`, sin escribir en `golden_dataset_runs`) | `test_ambiental_sanciones` (el miss de ruteo real de la corrida anterior) **ahora PASA** (`route=busqueda_por_ley`, `grounded=True`, pos=1) -- el fix de `fuzzy_ilike_pattern` funciono de verdad, no solo en la llamada aislada. El unico `failed` restante (`test_familiar_adulto_mayor_definicion`) sigue siendo el golden-dataset-desactualizado ya documentado (el sistema ahora responde con la ley correcta -- Adultos Mayores, Art.3 -- en vez de la fuente vieja Atencion a la Familia Art.2 que el test todavia espera; es una MEJORA real del sistema, no un bug). Sin fallos nuevos, sin regresion -- comparable o mejor que el mejor baseline documentado (`PLAN.md` Fase 6, 22/2/0, aunque ese fue medido antes de ingerir las 2 leyes nuevas). Se deja la decision de reactivar por defecto al usuario -- la condicion tecnica para reconsiderarlo ya esta cumplida | Decision pendiente del usuario: cambiar `agentic_rag.enabled` a `true` en `ai_config.json` (cambio de comportamiento por defecto para trafico real ya existente en Telegram, no solo un experimento) |
| `agentic_rag.self_reflection.enabled` | Implementado (Fase 7 Etapa 2), medido en vivo | Se disparo 1 de 5 veces en la corrida real, no cambio el resultado final, costo ~2x tiempo esa pregunta — sin mejora medida que justifique el costo por defecto | Acumular mas preguntas reales donde el gate primario sea True y el segundo gate degrade a False (los 3 casos de falso-positivo conocidos ya se resuelven gratis por otra ruta, no sirven de prueba) |
| `hyde.enabled` | **Ya esta en `true`** (unico de los tres activo) | N/A — activo porque fue el que si demostro beneficio medido (rescato el caso sucesion/Art.1576) | N/A |

Ver `PLAN.md` Fase 7 para el detalle completo y la evidencia cruda de cada medicion.

### B. Evaluado con evidencia real y RECHAZADO (no reabrir sin datos nuevos)

| Item | Por que se rechazo | Donde esta la evidencia |
|---|---|---|
| Contextual Retrieval (version cara, LLM por chunk) | La version barata (prefijo deterministico de Titulo/Capitulo) ya dio resultado negativo en el caso mas dificil conocido (Art.1576) — no se justifica gastar en la version cara sin que la barata funcione | `PLAN.md` Fase 6 |
| Pre-check de similitud para saltar HyDE en preguntas "sin esperanza" | Medido: los 4 casos genuinamente sin respuesta y el unico caso rescatado ocupan la MISMA banda de similitud (0.44-0.49) — ningun umbral separa ambos grupos con seguridad | `PLAN.md` Fase 6, seguimiento post-Fase 7 |
| WhatsApp bot (Baileys/OpenWA) | Discutido con el usuario: la motivacion real era mostrar soporte multicanal a reclutadores, no demanda de usuarios. Sin API oficial gratuita, requiere vincular un numero real por QR con riesgo de baneo. La arquitectura (`BaseBot`) ya queda lista para esto sin necesitar el canal en vivo | `PLAN.md` Fase 5 |
| Reintento del agente CAMBIANDO de ruta de busqueda (en vez de solo reformular texto) | Probado en vivo: reintroduciria el mismo patron de falso-positivo por lenguaje generico que la ruta `busqueda_por_ley` ya evita gratis en 2 de 3 casos documentados | `PLAN.md` Fase 7 Etapa 2 |

### C. Diferido explicitamente, esperando una condicion especifica (no un "algun dia" vago)

| Item | Condicion para retomarlo | Fuente |
|---|---|---|
| Clasificador de grounding — opcion 3: `found_answer` autodeclarado en la misma llamada de generacion | Pendiente validar primero si structured output es confiable en los 5 proveedores del fallback (la pregunta que el propio usuario marco como la correcta a resolver antes). Las opciones 1+2 (chunks reales + few-shot) ya dieron 22/2/0, cero fallas duras — no hizo falta la opcion 3 todavia | `PLAN.md` Fase 3.7 |
| Parent-child retrieval (buscar con chunks chicos, responder con articulo/seccion completa) | Solo si el dashboard de metricas muestra respuestas que citan fragmentos sueltos sin contexto suficiente | `LexChiapas_Formato_y_Mejoras_Futuras.md` Parte 2, referenciado en `PLAN.md` Fase 6 |
| Reranking con cross-encoder o LLM-as-judge (mejora sobre el reranker actual) | Solo si el reranking actual deja fuera del top chunks que si eran relevantes, visible en metricas reales | idem |
| Correccion ortografica antes de reescribir la pregunta | Solo si usuarios reales escriben con errores que degradan la busqueda — no hay señal de esto todavia (no hay trafico real de usuarios) | idem |
| Restriccion de cache semantico a preguntas sin `conversation_history` | No es un bug, es una limitacion de diseño actual. Si el patron real de uso en Telegram muestra que la mayoria de preguntas utiles SI llevan historial, ahi valdria la pena extender el cache para soportarlo | Conversacion de esta sesion (semantic_cache), no tiene item propio en `PLAN.md` todavia — agregarlo si se retoma |

### A/B/C — Viabilidad real de retomarlos ahora (analizado 2026-07-24)

Revision honesta de los 12 items de A/B/C contra el estado REAL actual del
proyecto (no una relectura optimista): `SELECT count(*) FROM conversations
GROUP BY platform` da `telegram=1, web=2` (3 conversaciones reales en TOTAL,
7 mensajes `assistant`). El proyecto sigue sin trafico real de produccion
porque la Fase 4 del roadmap (Parte 2, punto 4 — deploy real) todavia no se
ejecuto. Esto importa porque **5 de los 7 items no-rechazados dependen de
la MISMA precondicion** (trafico real acumulado), no de trabajo de codigo:

| Item | Viabilidad ahora | Por que |
|---|---|---|
| A.1 `agentic_rag.enabled` (comparar contra las 24 preguntas completas) | **Comparacion COMPLETA (2026-07-25)** — ver hallazgo real abajo | **Hallazgo real importante**: `run_golden_dataset.py` (el endpoint `POST /admin/evaluation/run`) importa y llama DIRECTAMENTE `app.rag.rag_pipeline.answer_question` -- nunca lee `ai_config.json agentic_rag.enabled` ni pasa por `conversation_store.handle_turn`. El plan original de esta fila ("activar la bandera y volver a correr el endpoint") **no habria tenido ningun efecto** -- el evaluador siempre mide el pipeline lineal sin importar la bandera. Se corrigio con un script puntual (`_scratch_agentic_golden_run.py`, borrado despues de usar) que llama `answer_question_agentic` directamente sobre las 24 preguntas, reusando `evaluate_case` (misma logica de passed/xfailed/failed que el evaluador real) -- NO se escribio en `golden_dataset_runs` (ese esquema no distingue de que pipeline vino una fila, insertar ahi habria mezclado silenciosamente un resultado agentico con el historial lineal). **Resultado real: agentico 20 passed / 2 xfailed_known / 2 failed (27.6min) vs lineal 19/3/2 (28.8min, `run_id=3`)** -- comparable en conteo bruto, pero NO identico en que casos fallan: 1 de los 2 `failed` del agente (`test_familiar_adulto_mayor_definicion`) es el MISMO golden-dataset-desactualizado que ya afectaba al lineal (no es diferencia real); el otro `failed` del lineal (Ley Federal del Trabajo, excepcion de red) NO se repitio en el agente (paso limpio, consistente con "no reproducible"); pero el agente introdujo **1 miss nuevo que el lineal NO tenia**: `test_ambiental_sanciones` -- el nodo "decidir" eligio la ruta `busqueda_por_ley` (acotada a una sola ley) y no encontro nada (`grounded=False` en 17.3s), mientras que el lineal (busqueda general sin acotar) si lo encontraba. Es un miss real de RUTEO del agente (la ley elegida por el LLM "decidir" no matcheo bien via ILIKE), no un problema de retrieval en si. **Veredicto original**: no hay evidencia de regresion generalizada, pero tampoco hay evidencia suficiente para reactivar por defecto todavia -- este miss especifico de ruteo deberia investigarse antes de la proxima decision. **FIX APLICADO Y VERIFICADO (2026-07-25)**: causa raiz confirmada con precision -- el nodo "decidir" devolvio `law_name="ley ambiental de chiapas"` (parafraseado de la pregunta del usuario), pero el nombre real es `"Ley Ambiental para el Estado de Chiapas"` (con "para el Estado" de mas en medio). Confirmado con SQL real: `ILIKE '%ley ambiental de chiapas%'` -> 0 filas; `ILIKE '%ley%ambiental%de%chiapas%'` (fuzzy) -> 1 fila. El fix (`fuzzy_ilike_pattern`, ya existia pero solo se usaba en `query_graph`/Fase 8) se centralizo en `app/rag/retriever.py` y se aplico tambien a `dense_search`/`sparse_search` (de las que depende `search_by_law`, la funcion que fallaba) y a `get_article`. Verificado en vivo: `search_by_law(db, "ley ambiental de chiapas", ...)` paso de 0 a 5 chunks, con el Art.214 esperado en el resultado (`passed_threshold=True`). `pytest` 46/46. **Pendiente real**: repetir la comparacion agentica completa (24 preguntas) para confirmar que el fix elimina el miss de `test_ambiental_sanciones` sin introducir nada nuevo -- no ejecutado todavia |
| A.2 `agentic_rag.self_reflection.enabled` | **BLOQUEADO** (trafico real) | Necesita acumular preguntas reales donde el gate primario de True degrade a False — con 7 mensajes `assistant` totales no hay volumen para eso |
| C.1 Grounding classifier opcion 3 (`found_answer` autodeclarado) | **Experimento CORRIDO (2026-07-25) -- condicion original CUMPLIDA en 4/5 proveedores** | Script de un solo uso, 5 proveedores x 2 casos (chunk real que SI responde / chunk real de OTRO tema que NO responde), `response_format={"type":"json_object"}` pidiendo `{"answer", "found_answer"}`. Resultado real: **`minimax-m3`, `glm-5.2`, `gpt-4o-mini`, `grok-4.20` -- los 4 aceptaron `response_format` sin error, devolvieron JSON valido, y `found_answer` coincidio con lo esperado en AMBOS casos (ni un falso positivo ni un falso negativo)**. `deepseek-v4-pro` fallo con timeout en los 2 casos (incluso reintentando SIN `response_format`) -- **inconcluso, no es evidencia de incompatibilidad con structured output**, es el mismo patron de latencia intermitente de NVIDIA NIM ya documentado varias veces en `PLAN.md` (la llamada nunca completo, asi que no se pudo evaluar el campo). Con 4/5 confirmados y el 5to inconcluso por infra (no por incompatibilidad real), la condicion que bloqueaba esta opcion esta esencialmente resuelta. **Decision pendiente, distinta del experimento**: construir esto de verdad significa tocar el camino de generacion PRINCIPAL (`app/rag/generator.py`), no un gate auxiliar como el clasificador actual -- requiere decision explicita del usuario antes de implementar, el experimento solo prueba que es TECNICAMENTE viable, no decide si vale la pena reemplazar el gate actual (que ya da 22/2/0, cero fallas duras) |
| C.2 Parent-child retrieval | **Revisado contra los 24 casos reales (2026-07-25) -- evidencia debil, replanteado** | Se leyo el contenido REAL de `chunks` para los articulos en disputa de los 24 casos del golden dataset (`run_id=3`). Descartado: ningun chunk viene truncado/fragmentado (341-882 caracteres, articulos completos siempre -- el chunker ya guarda el articulo entero, nunca lo corta) -- el caso "adulto mayor" (Art.2, 36 fracciones de definiciones) es el problema YA CONOCIDO de senal de embedding diluida (Fase 6), no fragmentacion, chunk unico completo. **Unico hallazgo real**: el caso de sucesion (Art.1573 vs 1576, Codigo Civil Libro Tercero) SI muestra que la respuesta completa vive repartida entre 2 articulos consecutivos -- Art.1573 dice CUANDO se abre la herencia legitima, Art.1576 dice QUIEN hereda (lo que la pregunta pide) -- y el retrieval a veces trae el 1573 (introductorio, semanticamente parecido) en vez del 1576 (el que responde de verdad). Es evidencia real pero de **1 caso de 24**, insuficiente para justificar la version generica de parent-child (chunks chicos + contexto completo al generar, que no aplica a este proyecto -- los chunks YA son articulos completos). Si se retoma, la tecnica correcta seria mas acotada: **expansion a articulos adyacentes** (traer N-1/N+1 como candidatos extra cuando el articulo principal no responda completo), no el parent-child clasico. Con n=1 no se recomienda construir esto todavia -- anotar y esperar mas senal real (deploy) antes de decidir |
| C.3 Cross-encoder/LLM-judge reranking | **BLOQUEADO** (trafico real) | Misma razon — necesita metricas reales de reranking fallando |
| C.4 Correccion ortografica | **BLOQUEADO** (trafico real) | El propio doc ya lo marcaba explicito: "no hay trafico real de usuarios" — sigue siendo cierto |
| C.5 Restriccion cache semantico a preguntas sin `conversation_history` | **BLOQUEADO** (trafico real) | Necesita patron real de uso en Telegram para decidir si vale la pena |
| B.1-B.4 (Contextual Retrieval caro, pre-check similitud, WhatsApp, cambio de ruta) | **Sin cambios, correctamente rechazados** | Revisado: ningun dato nuevo desde que se rechazaron (nada se volvio a tocar de esos temas) — se mantiene el criterio de no reabrir sin evidencia nueva, ver Parte 1.B |

**Conclusion (actualizada 2026-07-25):** de los 12 items, los 3 que no
dependian de deploy/trafico (A.1, C.1, C.2) ya se ejecutaron -- ninguno dio
un "activar ya" limpio: A.1 encontro un miss de ruteo nuevo del agente
(investigar antes de decidir), C.1 confirmo viabilidad tecnica pero deja la
decision de implementar pendiente del usuario, C.2 encontro evidencia real
pero insuficiente (1 caso de 24) para justificar la version generica. Los
otros 4 (A.2, C.3-C.5) comparten el mismo bloqueo real — vale mas la pena
priorizar la Fase 4 (deploy real, roadmap Parte 2 punto 4) que intentar
forzar cualquiera de estos sin la señal que su propia condicion pide. Los 4
de B siguen correctamente cerrados.

### D. Genuinamente sin empezar (huecos reales, bajo impacto conocido)

| Item | Impacto real conocido | Fuente |
|---|---|---|
| ~~`get_article`/`query_graph`: ILIKE de nombre de ley puede matchear multiples documentos sin desambiguar~~ **RESUELTO (2026-07-28)** | `get_article` ahora trae TODAS las filas que matchean (no `LIMIT 1` ciego); si mas de un documento distinto tiene ese mismo numero de articulo, prefiere un match EXACTO de nombre y si no hay, se rehusa a adivinar (`None`, mismo criterio "nunca inventa ni aproxima"). `query_graph` aplica el mismo criterio cuando se pide un `articulo` puntual (acota a un solo documento si hay match exacto; si no, mantiene el filtro amplio pero deja constancia con `logger.warning`). Verificado contra DB real: 0 colisiones reales hoy (los 4 libros del Codigo Civil confirmados sin numeracion repetida via SQL), pero el camino de desambiguacion se probo explicitamente pasando el nombre completo vs. uno parcial | `app/rag/agent_tools.py` |
| ~~2 variantes raras de marcador no cubiertas por la extraccion de Fase 8 ("SE DEROGA PUBLICADA", "REFORMADA REPUBLICADA")~~ **RESUELTO (2026-07-28) — HALLAZGO MAYOR al investigar**: lo que el documento original describia como "3 ocurrencias, trivial" resulto ser la punta de DOS familias de marcador completas sin cubrir: participio FEMENINO (`DEROGADA`/`REFORMADA`/`ADICIONADA`, el codigo solo reconocia la forma masculina) con **295 ocurrencias reales**, y verbo reflexivo "SE `<verbo>`" (`SE DEROGA`/`SE REFORMA`/`SE ADICIONA`, incluye el typo real `ADICONA` x3) con **141 ocurrencias reales** -- 436 relaciones nuevas sobre las 2017 previas (~20% de crecimiento del grafo). Verificado con SQL real antes y despues (dry-run sin tocar la DB primero, conteo exacto igual al de la corrida real), 0 marcadores sin tipo reconocido, 0 `to_document_id` NULL nuevos, suite de tests de `agent_tools`/`query_graph` sigue en verde (25/25), endpoint publico `/api/legal-relations` verificado con curl real mostrando las relaciones nuevas | `ingestion/extract_legal_relations.py` |
| ~~159 relaciones de `legal_relations` con `to_document_id` NULL~~ **RESUELTO (2026-07-24)** | Se ingirieron las 2 leyes (`Ley de Asistencia e Integracion de las Personas Adultas Mayores`, doc id=27, 93 articulos; `Ley para la Inclusion de las Personas con Discapacidad`, doc id=26, 57 articulos — patch de un typo real de PDF en Art.46/47 documentado en `load_ley_discapacidad.py`) y se re-corrio `extract_legal_relations.py`. `null to_document_id`: 159 -> 0 (89 resueltas contra Adultos Mayores, 70 contra Discapacidad). Total ahora 2017 relaciones, 21 documentos (20 activos), 8753 chunks | `ingestion/load_ley_adultos_mayores.py`, `ingestion/load_ley_discapacidad.py` |
| 131 leyes del Congreso de Chiapas sin ingerir (de 146 detectadas por el scraper) | Cobertura parcial del corpus — el proyecto ya es funcional con 18 leyes, esto es expansion de contenido, no un bug | `LexChiapas_Leyes_Pendientes_Congreso.md` |
| ~~Metricas basicas de uso en Telegram~~ **RESUELTO (2026-07-25)** | `questions_per_day_telegram`/`top_questions_telegram` en `/admin/metrics/usage`, `feedback_ratio_telegram` en `/admin/metrics/quality` — verificado con servidor real contra los 5 mensajes reales de Telegram existentes | `app/api/admin.py` |
| README profesional con demo/GIF | Fase 5 sin marcar — relevante para portafolio, bajo costo | `PLAN.md` Fase 5 |
| Deploy 24/7 del backend (Telegram) | Fase 5 sin marcar, distinto del deploy del stack web (ver fila siguiente) | `PLAN.md` Fase 5 |
| Deploy real del stack web (Railway/Render + Vercel) | **Preparacion completa, ejecucion pendiente del lado del usuario** (crear cuentas, setear env vars) — no es trabajo de codigo, son pasos manuales ya documentados paso a paso | `WEB_FRONTEND_PLAN.md` Fase D |
| ~~Verificacion visual/pixel real del dashboard (captura de pantalla)~~ **RESUELTO (2026-07-30), con 3 hallazgos reales corregidos** | Recorrido visual real (Chrome via claude-in-chrome) de Uso/Calidad/Performance/Guardrails/Agente/Explorar, con sesion real (login con `dev-admin-key`). Encontro y corrigio: **(1)** `dashboard/agente` crasheaba (`metrics.avg_intentos.toFixed is not a function` -- el backend serializa `avg_intentos` como string numerico, igual que `latency.avg_ms`, pero el codigo llamaba `.toFixed()` directo sin `Number(...)`); **(2)** la leyenda de la grafica de Golden Dataset mostraba "Passed" y "Xfailed conocido" con el MISMO verde (`--status-good` y `--series-4` son visualmente casi identicos), cambiado a `--series-3` (ambar); **(3)** hallazgo mas grande -- `/explorar` (paginas publica, fetch client-side) fallaba SIEMPRE en el navegador real (503, confirmado con `read_network_requests`) pese a que `curl` funcionaba perfecto -- causa raiz: `FRONTEND_ORIGIN=http://localhost:3000` en `.env` no coincide con el origen real del navegador en esta maquina (`http://127.0.0.1:3000`, la convencion ya establecida por el bug de IPv6 documentado), asi que CORS bloqueaba el fetch (`access-control-allow-origin` ausente de la respuesta) -- esto es una REGRESION del fix de CORS que Fase G dio por verificado el 2026-07-24 (esa verificacion fue con `curl -X OPTIONS` simulando el Origin, nunca con un navegador real en 127.0.0.1). Corregido a `FRONTEND_ORIGIN=http://127.0.0.1:3000`, re-verificado en navegador real: selector de 20 leyes carga, grafo hub-and-spoke de relaciones renderiza con las relaciones nuevas de la familia "SE VERBO" (fechas 2025-2026 reales). Tambien se detecto y descarto un servidor `next dev` huerfano (otro proceso, sin relacion, cache de rutas obsoleta causando 404 en `/api/admin/login`) y se agrego `allowedDevOrigins: ["127.0.0.1"]` a `next.config.ts` (Next.js 16 bloquea por defecto recursos dev cross-origin que no vengan de "localhost") | `lexchiapas-web/src/app/dashboard/agente/page.tsx`, `lexchiapas-web/src/app/dashboard/calidad/page.tsx`, `lexchiapas-web/next.config.ts`, `lexchiapas/.env` |
| ~~Columna `was_rewritten` en `messages`~~ **RESUELTO (backend confirmado 2026-07-24)** | `grounded_by_rewrite: {was_rewritten, grounded, total}[]` agregado a `/admin/metrics/quality`, verificado con `curl` real contra datos reales | `WEB_FRONTEND_PLAN.md` Fase E, `app/api/admin.py` |
| ~~Persistir `jailbreak_attempts`~~ **RESUELTO (backend confirmado 2026-07-24)** | Columna `messages.jailbreak_detected` agregada; `/admin/metrics/guardrails` ya devuelve el numero real (paso de `null` a `0`), verificado contra datos reales. Cero cambios de codigo necesarios del lado frontend — el `EmptyState` condicional ya estaba escrito para esta transicion | `WEB_FRONTEND_PLAN.md` Fase A/C.1, `PLAN.md` Fase 2.5 |
| ~~`/admin/login` sin rate-limiting~~ **RESUELTO (2026-07-24)** | `enforce_rate_limit` (ya existente en `app/api/rate_limit.py`) ahora se llama en `admin_login`, keyed por IP del cliente (`admin_login:<ip>`), ANTES de revisar la key. Verificado con servidor real: 10 intentos con key incorrecta -> 401, el intento #11 EN LA MISMA RAFAGA (sin hueco de tiempo) con la key CORRECTA -> 429 -- confirma que bloquea incluso credenciales validas una vez alcanzado el limite, no solo intentos fallidos | `app/api/admin.py` |
| ~~Fase F (Agent Trace en el frontend)~~ **RESUELTO (backend confirmado 2026-07-24)** | `AgentTrace` en `ChatResponse` (`app/schemas/chat.py`), columna `messages.agent_trace` JSONB, y `GET /admin/metrics/agent` implementados. Verificado end-to-end con una pregunta real (`agentic_rag.enabled` activado temporalmente, confirmado que persiste y que el endpoint lo refleja, revertida la bandera despues, diff byte-a-byte confirmo `ai_config.json` identico al original) | `app/rag/agent_pipeline.py`, `app/api/admin.py`, `app/models/message.py` |
| ~~Fase G (Explorador de relaciones legales, pagina publica `/explorar`)~~ **RESUELTO (backend confirmado 2026-07-24)** | `GET /api/laws` (20 leyes activas, verificado contra `count(*)` real) y `GET /api/legal-relations?law=` (nuevo `app/api/public.py`, reusa `query_graph` de `agent_tools.py` y `fuzzy_ilike_pattern` de `retriever.py` -- esta ultima se centralizo ahi el 2026-07-25, ver fila de `agentic_rag.enabled` arriba) implementados y verificados en ambas direcciones de la relacion (ley como origen Y como destino de una reforma) | `app/api/public.py`, `WEB_FRONTEND_PLAN.md` Fase G |
| ~~Listado navegable de errores de chat individuales (hoy solo el conteo agregado via `system_error_rate`)~~ **RESUELTO (backend ya existia, frontend conectado 2026-07-28)** | `recent_chat_errors` ya vivia en `/admin/metrics/performance` (junto con `latency_breakdown` y `primary_vs_fallback`, agregados por la sesion paralela) pero el frontend nunca los tipaba ni renderizaba -- se agregaron a `PerformanceMetrics` (`adminApi.ts`) y se conectaron en `performance/page.tsx` (tabla de errores de chat, stat tiles de latencia de busqueda/generacion, grafica primario-vs-fallback). Verificado con curl real contra el servidor: shape identico al `PerformanceMetrics` de TypeScript, `recent_chat_errors: []` (sin errores reales en los 7 mensajes existentes) | `app/api/admin.py`, `lexchiapas-web/src/lib/adminApi.ts`, `lexchiapas-web/src/app/dashboard/performance/page.tsx` |
| ~~Fase C.2 — 3 mejoras de dashboard diseñadas~~ **RESUELTO, los 3 (backend confirmado 2026-07-24 ~18:05, ya en codigo real, verificado leyendo `app/api/admin.py` directamente)**: (1) `primary_vs_fallback` en `/admin/metrics/performance`, deriva de `get_primary_model()` sin migracion; (2) `search_time_ms`/`generation_time_ms` ya son columnas reales en `messages` y ya se agregan (avg/p95) en `/admin/metrics/performance`; (3) golden dataset como endpoint real: `app/evaluation/golden_dataset.py` + `run_golden_dataset.py`, tablas `golden_dataset_runs`/`golden_dataset_run_cases` (1 fila real ya migrada), `POST /admin/evaluation/run` (Celery) + `GET /admin/metrics/golden_dataset` | `app/api/admin.py`, `app/evaluation/`, `app/workers/evaluation_tasks.py` |
| ~~Sin Alembic~~ **RESUELTO (2026-07-25)** | Alembic instalado y configurado (`alembic/env.py` lee `DATABASE_URL` real de `app.config`, `target_metadata=Base.metadata`). Revision baseline (`cf62d1f2007f_baseline_schema_real.py`) generada por `autogenerate` contra la DB real -- **diff completamente vacio** (confirma que los modelos SQLAlchemy ya coincidian exacto con las 10 tablas reales, sin drift que corregir), aplicada con `alembic stamp head` (no `upgrade`, para no tocar nada que ya existe). Probado de punta a punta con una tabla de prueba reversible (`revision --autogenerate` -> `upgrade head` -> `downgrade -1`, confirmado que se creo y se borro limpio), datos reales verificados sin cambios (`documents=21, chunks=8753, conversations=3, messages=14`). Politica de aca en adelante documentada en `alembic/README`: modelos se cambian -> `alembic revision --autogenerate` -> revision manual del diff -> `alembic upgrade head`, se acabo el `ALTER TABLE` manual sin rastro | `alembic/`, `app/config.py` |

---

## Parte 2 — Roadmap propuesto (nuevo, bajo costo / alto valor)

Con las 8 fases del backend y las 7 del frontend web (A-G) completas, esto
ya no es "que falta para que funcione" sino "que vale la pena antes de
mostrarlo".
Orden sugerido por costo/beneficio, no por dependencia tecnica salvo donde
se indique:

1. ~~**Ingerir las 2 leyes que resuelven 159 relaciones huerfanas del
   grafo**~~ **HECHO (2026-07-24)** — Ley de Asistencia e Integracion de las
   Personas Adultas Mayores (doc id=27) y Ley para la Inclusion de las
   Personas con Discapacidad (doc id=26) ingeridas, mismo patron
   `ingestion/load_*.py` ya usado 14 veces. `legal_relations` con
   `to_document_id` NULL: 159 -> 0. Ver Parte 1.D para el detalle completo.
   `[Subagente: data-extraction]`
2. ~~**Cerrar los 3 pedidos de backend que ya tienen frontend construido y
   esperando**~~ **HECHO (2026-07-24)** — `grounded_by_rewrite` en
   `/admin/metrics/quality`, `AgentTrace`/`messages.agent_trace`/
   `GET /admin/metrics/agent`, y `GET /api/laws`+`GET /api/legal-relations`
   implementados y verificados contra datos reales (ver Parte 1.D).
   `[Subagente: logic]`
3. ~~**Cerrar el hallazgo de rate-limiting en `/admin/login`**~~ **HECHO
   (2026-07-24)** — `enforce_rate_limit` conectado en `admin_login`, keyed
   por IP, verificado con servidor real (10 intentos fallidos -> 429,
   incluso con la key correcta en la misma rafaga).
4. **Deploy real** (backend en Railway/Render, frontend ya listo en Vercel
   segun `WEB_FRONTEND_PLAN.md` Fase D) — la preparacion ya esta completa,
   son pasos de ejecucion, no de diseño. Prerequisito para que el README
   pueda linkear una demo publica.
5. **README profesional + demo/GIF** (Fase 5 pendiente) — depende
   parcialmente del punto 4 si se quiere linkear el chat en vivo, pero el
   GIF/capturas del bot de Telegram funcionando ya se pueden grabar hoy sin
   esperar el deploy.
6. **Adoptar Alembic** antes de que la siguiente fase nueva agregue otra
   migracion manual mas — cada fase nueva desde que se escribio este
   documento siguio agregando columnas a mano (`jailbreak_detected`,
   `was_rewritten`, y las que pide el punto 2 arriba), es el momento mas
   barato de hacerlo (schema todavia chico), se vuelve mas caro cuanto mas
   se espera. `[Subagente: database]`
7. ~~**Metricas basicas de uso en Telegram**~~ **HECHO (2026-07-25)** —
   `questions_per_day_telegram` y `top_questions_telegram` agregados a
   `GET /admin/metrics/usage`, `feedback_ratio_telegram` agregado a
   `GET /admin/metrics/quality` (JOIN `messages`->`conversations` por
   `platform='telegram'`, ya que `messages` no tiene columna `platform`
   propia). Verificado con servidor real contra los 5 mensajes reales de
   Telegram existentes. Sigue siendo la fuente de datos que las 3 mejoras
   condicionadas de RAG (seccion C arriba) necesitan para decidirse con
   evidencia real conforme se acumule mas trafico. `[Subagente: logic]`
8. ~~**Reevaluar `agentic_rag`**~~ **CONFIRMADO (2026-07-25)** — miss de
   ruteo encontrado (`test_ambiental_sanciones`) y corregido
   (`fuzzy_ilike_pattern` en `app/rag/retriever.py`), re-corrida completa de
   las 24 preguntas confirmo el fix (21 passed/2 xfailed_known/1 failed, el
   unico failed es golden-dataset-desactualizado, no un bug real). Ver
   Parte 1.A. **Decision de activar `agentic_rag.enabled=true` por defecto
   queda pendiente del usuario** -- la condicion tecnica ya esta cumplida,
   pero es un cambio de comportamiento sobre trafico real existente en
   Telegram, no solo un experimento. `self_reflection.enabled` sigue
   bloqueado en trafico real acumulado (punto 7, ahora con metricas de
   Telegram ya disponibles para monitorearlo) — no antes, seria repetir el
   mismo error que el proyecto ya evito con HyDE/reranker: no activar sin
   medir.
9. ~~**Golden dataset como endpoint automatizado**~~ **HECHO (backend
   confirmado 2026-07-24, frontend conectado 2026-07-28)** — ver Parte
   1.D, fila Fase C.2. `ragAdvancedSnapshot.ts` ya NO tiene el golden
   dataset estatico (solo conserva las tecnicas de `ai_config.json`, que
   siguen siendo flags manuales sin endpoint propio) -- `dashboard/calidad`
   ahora consume `GET /admin/metrics/golden_dataset` en vivo (ultima
   corrida real + tendencia de las ultimas 10 + detalle por caso),
   verificado con curl real contra el servidor (`run_id=3`, 19/3/2 de 24).
10. **Expandir la ingesta de las 131 leyes restantes del Congreso** — el
    trabajo de mayor volumen pero menor urgencia; el corpus actual (18
    leyes) ya demuestra el sistema de punta a punta, esto es cobertura de
    contenido, no una limitacion tecnica.

**No incluidos a proposito** (ya evaluados y rechazados con evidencia, ver
Parte 1.B): Contextual Retrieval version cara, pre-check de similitud para
HyDE, WhatsApp, cambio de ruta en el reintento del agente. No reabrir sin
datos nuevos que contradigan la evidencia ya medida.
