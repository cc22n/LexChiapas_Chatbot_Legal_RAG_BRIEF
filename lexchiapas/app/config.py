import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

AI_CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai_config.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    nvidia_api_key: str = ""
    # Proveedores de LLM adicionales, usados solo como ultimo recurso en
    # app.llm.router.generate_with_fallback (ver ai_config.json llm.providers
    # y llm.fallback_order). openai_api_key/xai_api_key tienen creditos
    # limitados ($5 c/u, verificados 2026-07-09). gemini_api_key/
    # groq_api_key existen para cuando esas cuentas esten utilizables
    # (Groq: key vencida; Gemini: cuota 0 en el tier gratis actual) -- hoy
    # NO estan en fallback_order, no se gasta nada de ellas todavia.
    openai_api_key: str = ""
    xai_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    # Reranking real (Fase 3.7): NVIDIA NIM primero, Jina como 2do nivel de
    # fallback (ver app/rag/reranker_router.py y ai_config.json
    # reranking.fallback_order). nvidia_api_key ya existe arriba, se reusa.
    jina_api_key: str = ""
    database_url: str = "postgresql+psycopg://lexchiapas:password@localhost:5432/lexchiapas"
    redis_url: str = "redis://localhost:6379/0"

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    whatsapp_api_token: str = ""

    admin_api_key: str = ""
    # Firma las cookies de sesion del dashboard admin (POST /admin/login). Si
    # se deja vacio, se usa admin_api_key como llave de firma (valido para
    # fase 1/uso personal; si el proyecto crece a multi-usuario real, generar
    # una SECRET_KEY propia y separada del admin_api_key).
    secret_key: str = ""
    # Origen del frontend Next.js (lexchiapas-web) para CORS. Vacio = sin
    # CORS habilitado (solo llamadas same-origin/Telegram/admin por header).
    frontend_origin: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_ai_config() -> dict:
    with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
