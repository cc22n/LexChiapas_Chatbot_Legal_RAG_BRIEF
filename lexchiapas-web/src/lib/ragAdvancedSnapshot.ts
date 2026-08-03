// Instantanea MANUAL de las tecnicas de RAG avanzado (ai_config.json) --
// esto SI sigue siendo manual a proposito: son flags de configuracion, no
// resultados de una corrida, y no hay endpoint que los exponga (ni se pidio
// uno). El golden dataset en si ya NO vive aca -- ver
// GET /admin/metrics/golden_dataset (adminApi.ts, getGoldenDatasetMetrics),
// consumido en dashboard/calidad/page.tsx con datos reales en vivo.
export const RAG_ADVANCED_SNAPSHOT = {
  techniques: [
    {
      name: "Query rewriting",
      active: true,
      detail: "Reescribe seguimientos cortos (<=6 palabras) con historial de conversacion",
    },
    {
      name: "HyDE",
      active: true,
      detail: "ai_config.json: hyde.enabled=true -- respuesta hipotetica reemplaza el embedding de busqueda densa",
    },
    {
      name: "Reranking real",
      active: true,
      detail: "NVIDIA NIM (llama-nemotron-rerank) -> Jina -> heuristica local",
    },
    {
      name: "Contextual retrieval (version cara, LLM por chunk)",
      active: false,
      detail: "Version barata evaluada, mejora dentro del ruido -- no se implementa la version cara sin evidencia",
    },
  ],
};
