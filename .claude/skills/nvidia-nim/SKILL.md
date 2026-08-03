---
name: nvidia-nim
description: Reference for using NVIDIA NIM as the embeddings + LLM provider in LexChiapas. Use when writing or debugging code in app/llm/providers.py, app/llm/router.py, app/rag/embeddings.py, or ai_config.json.
---

# NVIDIA NIM — referencia rapida

Proveedor de embeddings y LLM para LexChiapas. Free tier, sin tarjeta,
compatible con el SDK de OpenAI.

## Conexion

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],  # empieza con nvapi-
)
```

Compatible directo con LangChain via su integracion OpenAI-compatible.

## Modelos usados en este proyecto

- **Embeddings:** NV-Embed
- **LLM (orden de fallback sugerido):**
  1. MiniMax M2.7
  2. DeepSeek 3.2
  3. GLM 5.1

El catalogo de NVIDIA cambia con poco aviso (pueden deprecar modelos). Por
eso el orden de fallback vive en `ai_config.json`, NUNCA hardcodeado en
Python. Cambiar de modelo = editar el JSON, no el codigo.

## Limites y advertencias

- ~40 RPM en el free tier (ampliable a 200). Suficiente para uso personal/
  portafolio, no para trafico masivo real. Si el bot tiene multiples
  usuarios concurrentes, aplicar rate limiting propio para no agotar la
  cuota compartida.
- Un 403 en un modelo especifico usualmente significa que hace falta
  registrarse para esa familia de modelo en su pagina ("Try API") en
  build.nvidia.com.
- Es para desarrollo/testing/portafolio, no para produccion con usuarios
  reales masivos.
- Si NVIDIA falla por completo, el fallback opcional configurado es Gemini
  free tier.

## Al escribir codigo que llama a NIM

- Siempre leer el modelo activo desde `ai_config.json`, iterar el fallback
  list en orden, y solo pasar al siguiente si el actual falla (error, 403,
  timeout) — no asumir que el primero siempre esta disponible.
- Loggear que modelo respondio (para `messages.llm_model` en la DB).
- Dimension del vector de embeddings debe coincidir entre ingestion y query;
  si cambia el modelo de embeddings, hay que re-generar embeddings existentes
  (no solo los nuevos).
