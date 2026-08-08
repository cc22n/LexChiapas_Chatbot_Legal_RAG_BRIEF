import json
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AI_CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai_config.json"

# Default dummy de desarrollo -- placeholder solo para poder levantar la app
# localmente sin .env. Se referencia tambien desde el validador de abajo
# para detectar si sigue puesto sin cambiar fuera de development.
_DEV_DATABASE_URL_DEFAULT = "postgresql+psycopg://lexchiapas:password@localhost:5432/lexchiapas"


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
    database_url: str = _DEV_DATABASE_URL_DEFAULT
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

    @model_validator(mode="after")
    def _require_critical_config_outside_development(self) -> "Settings":
        """BUG REAL (auditoria de salud del backend, 2026-08-06, hallazgo
        M4): sin esto, la app arrancaba limpio (sin error) aunque faltaran
        variables criticas para operar de verdad -- el primer sintoma real
        llegaba recien en el primer request (401 de NVIDIA, connect timeout
        de Postgres contra el default dummy de development), no en el log
        de arranque del proceso. Solo aplica fuera de development: el
        default dummy de database_url existe justo para poder levantar la
        app local sin .env.
        """
        if self.environment == "development":
            return self

        missing = []
        if not self.database_url or self.database_url == _DEV_DATABASE_URL_DEFAULT:
            missing.append("database_url")
        if not self.nvidia_api_key:
            missing.append("nvidia_api_key")
        if not self.admin_api_key:
            missing.append("admin_api_key")

        if missing:
            raise ValueError(
                f"Configuracion critica faltante para environment={self.environment!r}: "
                f"{', '.join(missing)}. Definila en .env o en las variables de entorno del deploy."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_ai_config() -> dict:
    with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
