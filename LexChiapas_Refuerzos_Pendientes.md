# LexChiapas_Refuerzos_Pendientes.md

Documento fuente aparte (no toca `PLAN.md` directamente). Cubre 4 puntos
de refuerzo identificados en sesion de planificacion, sobre trabajo que
YA estaba anotado como pendiente en `PLAN.md`/`WEB_FRONTEND_PLAN.md` pero
sin priorizar, mas uno nuevo. Para que quien retome `PLAN.md` los integre
donde corresponda.

---

## 1. Golden dataset / set de regresion (PRIORIDAD MAS ALTA)

Ya estaba anotado en Fase 2 de `PLAN.md` y marcado como "#1 indispensable,
el mas grande" en `WEB_FRONTEND_PLAN.md` - pero sigue sin existir de forma
formal, solo las 6-8 preguntas ad hoc usadas para validar bugs de Fase 1/2.

Razon para subir la prioridad: el reranker real y el cache semantico (ver
`LexChiapas_Reranker_y_Cache_Semantico.md`) se justifican con "deberia
mejorar la calidad" - sin este set no hay forma de medirlo, solo de
asumirlo. Implementar ANTES o junto con el reranker, no despues.

- [ ] Armar 15-20 preguntas con respuesta esperada (articulo correcto o
      "no encontrado"), cubriendo las leyes ya cargadas (Amnistia,
      Bibliotecas, Tortura, Adopcion) `[Subagente: logic]`
- [ ] Automatizar como test (pytest), corriendo el pipeline actual como
      baseline documentado `[Subagente: logic]`
- [ ] Usar este mismo set para medir el reranker real y el cache
      semantico cuando se implementen, en vez de asumir la mejora
      `[Subagente: logic]` + `[Subagente: bugs]` si algo falla

**Entregable:** set de regresion automatizado + resultado baseline
documentado, listo para comparar contra cualquier cambio futuro al RAG.

---

## 2. Manejo de errores en el pipeline de chat (gap ya diagnosticado)

Ya esta identificado explicitamente en `WEB_FRONTEND_PLAN.md` (item #3 de
la tabla de metricas): cero `try/except` alrededor de `answer_question()`
en `app/bots/conversation_store.py` y `app/api/chat_web.py`. Hoy una
excepcion a mitad del pipeline tira 500 sin dejar rastro en la DB -
"no encontre informacion" (`found_answer=false`, resultado valido) y
"el sistema fallo" (excepcion real) son indistinguibles porque la
segunda no se guarda en ningun lado.

- [ ] Agregar manejo de errores alrededor de `answer_question()` en
      `conversation_store.py` (usado por Telegram y web via
      `handle_turn()`) `[Subagente: logic]`
- [ ] Persistir el error de forma distinguible de un `grounded: False`
      legitimo - columna o tabla nueva, mismo patron que
      `ingestion_logs.status/error_message` `[Subagente: database]`
- [ ] Exponer la tasa de fallas reales en el dashboard (Performance),
      separado de la tasa de "no encontre informacion" `[Subagente: logic]`

**Entregable:** fallas reales del sistema visibles y distinguibles de
respuestas "no encontrado" legitimas, en vez de 500 silenciosos.

---

## 3. Seguridad del contenido scrapeado (prompt injection)

Ya esta en el checklist de Fase 2 de `PLAN.md`, sin marcar: confirmar que
el texto legal scrapeado no pueda romper la estructura del prompt
(inyeccion via documento legal malformado, encabezados falsos, etc.).

- [ ] Correr una auditoria de seguridad sobre `app/rag/generator.py` y
      los scrapers (`ingestion/scrapers/`) enfocada en prompt injection
      desde contenido scrapeado `[Subagente: security-guardian]`
- [ ] **Si el agente `security-guardian` no esta disponible en esta
      sesion/entorno** (verificar con `/agents`), crear uno nuevo con ese
      mismo enfoque (OWASP, inyeccion, XSS/CSRF) **como agente de
      PROYECTO** en `.claude/agents/security-guardian.md` dentro del
      repo de LexChiapas - no solo en `~/.claude/agents/` global. Esto lo
      deja versionado junto con el codigo, disponible sin depender de
      configuracion personal fuera del repo.
- [ ] Al invocarlo, nombrarlo explicitamente en el prompt ("Usa el agente
      security-guardian para...") en vez de confiar solo en
      delegacion automatica por descripcion - mas confiable para este
      tipo de tarea critica.

**Entregable:** auditoria de seguridad documentada sobre el contenido
scrapeado, y `security-guardian` disponible como agente de proyecto
versionado (no solo global) para auditorias futuras.

---

## 4. Limitacion conocida: `congreso_scraper.py` no funciona (no urgente)

Documentado en `PLAN.md` (Fase 1 y notas finales): la pagina de
legislacion vigente del Congreso del Estado carga el listado por
JavaScript, `requests` no lo ve. Hoy no bloquea nada porque
`consejeria_scraper.py` solo (139 leyes) cubre el corpus necesario.

- [ ] No resolver ahora. Solo mantener anotado que el corpus actual
      depende 100% de Consejeria Juridica - si en el futuro se necesita
      algo que solo exista en el sitio del Congreso, este hueco va a
      aparecer y requerira Selenium/Playwright (dependencia nueva, hoy
      no esta en `requirements.txt`) `[Subagente: data-extraction]`
      cuando se decida abordarlo.

---

## Orden sugerido de implementacion

1. Golden dataset (habilita medir todo lo demas)
2. Manejo de errores (barato, cierra un gap real de observabilidad)
3. Reranker real + cache semantico (ver documento aparte, medidos contra
   el golden dataset del punto 1)
4. Auditoria de seguridad del scraping
5. Congreso scraper: diferido, sin fecha
