  #  │          Tarea          │                                               Por qué                                               │               Estado                │
├─────┼─────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ 1   │ Código Civil (Libro     │ En progreso, terminar antes de empezar algo nuevo                                                   │ 1293 chunks guardados hasta ahora,  │
│     │ Cuarto)                 │                                                                                                     │ sigue corriendo                     │
├─────┼─────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ 2   │ Golden dataset / set de │ La más importante — sin esto, cualquier mejora al RAG (reranker, caché) se mide "a ojo" en vez de   │ Confirmado que no existe, pendiente │
│     │  regresión              │ con evidencia real                                                                                  │  en 2 fases de PLAN.md              │
├─────┼─────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ 3   │ Manejo de errores en el │ Barato de arreglar, y es peor de lo que pensábamos: hoy un crash real pierde la pregunta del        │ Confirmado, cero try/except         │
│     │  pipeline de chat       │ usuario sin dejar rastro en la DB                                                                   │                                     │
├─────┼─────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ 4   │ Scraper de Congreso     │ Subir prioridad — ya nos mordió una vez con el Código Fiscal (Consejería no lo tenía)               │ Confirmado el mismo bloqueo         │
│     │                         │                                                                                                     │ técnico, pero ya no es "no urgente" │
├─────┼─────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ 5   │ Reranker real           │ Ya viable con el modelo correcto que encontraste (nvidia/llama-nemotron-rerank-vl-1b-v2, probado y  │ Desbloqueado                        │
│     │                         │ funcionando), pero se mide contra el golden dataset del punto 2, no antes                           │                                     │
├─────┼─────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ 6   │ Caché semántico         │ Depende de que el reranker/threshold estén estables primero (si no, cachea respuestas con un        │ Viable, va al final                 │
│     │                         │ criterio que luego cambia)                                                                          │                                     │
├─────┼─────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ 7   │ Auditoría de seguridad  │ Ya resuelto sin trabajo nuevo — se usa el agente security existente cuando llegue el momento, no    │ Sin bloqueo, baja urgencia          │
│     │ (prompt injection)      │ hace falta crear nada                                                                               │                                     │
└─────┴─────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘