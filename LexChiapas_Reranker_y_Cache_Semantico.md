# LexChiapas_Reranker_y_Cache_Semantico.md

Documento fuente aparte (no toca `PLAN.md` directamente). Cubre dos mejoras
acordadas en sesion de planificacion, para que quien retome `PLAN.md`
las integre donde corresponda (sugerido: como Fase 2.7 y Fase 2.8, mismo
patron que Fase 2.5 Guardrails y Fase 2.6 Memoria conversacional).

---

## 1. Reranker real (reemplaza el placeholder de `app/rag/reranker.py`)

Objetivo: reemplazar la heuristica de solapamiento de palabras por un
cross-encoder real, con fallback multi-proveedor (mismo patron que
`app/llm/router.py` ya usa para el LLM).

**Orden de fallback:**
1. NVIDIA NIM - `nvidia/llama-3.2-nv-rerankqa-1b-v2` (endpoint
   `/v1/ranking`). Multilingue, contexto 8192 tokens. Ya se tiene la API
   key.
2. Jina AI - `jina-reranker-v2-base-multilingual`. Ya registrado, 10M
   tokens gratis compartidos con el resto de APIs de Jina. Runway
   estimado: ~1000-1400 llamadas de rerank con el corpus actual. Tier
   gratis es no-comercial.
3. Heuristica local actual (`app/rag/reranker.py` tal cual existe hoy)
   como ultimo recurso si ambos proveedores externos fallan.

**Checklist:**
- [ ] Crear `app/rag/reranker_router.py` con logica de fallback igual a
      `app/llm/router.py`, orden leido desde `ai_config.json`
      (seccion nueva `reranking.fallback_order`) `[Subagente: logic]`
- [ ] 1 intento por proveedor, timeout corto (5-8s, no 60s como el LLM -
      el rerank es una llamada mas liviana). Sin reintentos multiples por
      proveedor, para no repetir el cuelgue que ya se arreglo en el
      cliente de NVIDIA `[Subagente: logic]`
- [ ] Normalizar el output de cada proveedor a un ranking ordinal
      (posicion 1, 2, 3...) antes del top-K - los scores de NVIDIA
      (logit), Jina y la heuristica local no son comparables entre si
      `[Subagente: logic]`
- [ ] Recalibrar `similarity_threshold` (hoy 0.5, calibrado sobre el
      score dense crudo) para la escala del reranker externo - repetir
      el ejercicio empirico de Fase 2 con las 15-20 preguntas de prueba
      `[Subagente: logic]`
- [ ] Separar el timing de retrieval vs reranking vs generacion en
      `response_time_ms` (hoy es un solo timer) - lo necesita tambien el
      dashboard, ver item #5 de `WEB_FRONTEND_PLAN.md`
      `[Subagente: logic]`
- [ ] Set de regresion (15-20 preguntas, automatizadas) corrido contra
      pipeline viejo vs nuevo, comparando `grounded` y articulo citado,
      para medir la mejora real sobre el corpus propio
      `[Subagente: logic]` + `[Subagente: bugs]` si algo falla

**Entregable:** reranker real con fallback de 3 niveles y evidencia
medida (no asumida) de mejora sobre el baseline actual.

---

## 2. Cache semantico (mejora nueva, no estaba en el plan original)

Objetivo: reducir llamadas a retrieval+LLM en preguntas repetidas o
parafraseadas, reusando el embedding que ya se calcula por pregunta.

**Checklist:**
- [ ] Tabla nueva `semantic_cache` en Postgres (mismo patron que las 6
      tablas existentes): `question_embedding vector(1024)`,
      `question_text`, `response_json` (respuesta + citas + disclaimer),
      `source_document_ids` (array), `created_at`, `hit_count`,
      `last_used_at` `[Subagente: database]`
- [ ] Antes del hybrid search: comparar embedding de la pregunta contra
      `semantic_cache` con `<=>` de pgvector, umbral CONSERVADOR
      (0.95-0.97, mas estricto que el 0.5 de retrieval - un falso
      positivo aqui devuelve la respuesta de una ley equivocada)
      `[Subagente: logic]`
- [ ] Si hay match: devolver respuesta cacheada, incrementar `hit_count`
      y `last_used_at`, sin tocar retrieval ni LLM. Si no hay match:
      pipeline completo normal, y al final insertar en `semantic_cache`
      `[Subagente: logic]`
- [ ] Invalidacion: cuando `ingestion_logs` marca un documento
      re-ingerido/actualizado, invalidar las entradas de `semantic_cache`
      cuyo `source_document_ids` lo incluya. Alternativa mas simple para
      MVP: TTL de 30 dias, sin invalidacion por documento
      `[Subagente: database]`
- [ ] Decidir si se cachean tambien respuestas `grounded: False`
      ("no encontre informacion") - probablemente si, ahorran costo en
      preguntas repetidas fuera de dominio `[Subagente: logic]`
- [ ] Metrica nueva para el dashboard: `cache_hit_rate` - encaja en la
      vista de Performance de `WEB_FRONTEND_PLAN.md` junto a
      `tokens_per_day` `[Subagente: logic]`

**Entregable:** cache semantico con umbral conservador e invalidacion
basica, mas `cache_hit_rate` visible en el dashboard.

---

## Nota de orden

El cache semantico depende de que el reranker/threshold esten estables
primero. Si el threshold se recalibra despues de tener cache poblado, las
entradas viejas quedan con respuestas generadas bajo el threshold
anterior. Implementar reranker primero, cache despues.
