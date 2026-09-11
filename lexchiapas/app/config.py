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
    # Chat de Telegram al que la tarea de alerta (app.workers.alerting_tasks)
    # manda avisos operativos -- ej. modelo de embeddings muerto, o pico de
    # turnos con error de sistema (Fase 9.8/C3). Vacio = alertas desactivadas
    # (se loguea el diagnostico igual, solo no se envia a Telegram).
    admin_telegram_chat_id: str = ""

    admin_api_key: str = ""
    # Firma las cookies de sesion del dashboard admin (POST /admin/login). En
    # development, si se deja vacio, admin_auth._signing_key cae en
    # admin_api_key (comodo para uso local). FUERA de development es
    # OBLIGATORIA y debe ser DISTINTA de admin_api_key (ver el validador de
    # abajo y el hallazgo del pentest): reusar la admin key como llave de
    # firma permite forjar sesiones offline si esa key se filtra. Generar con
    # `python -c "import secrets; print(secrets.token_hex(32))"`. El frontend
    # (lexchiapas-web) debe usar EXACTAMENTE la misma SECRET_KEY para que sus
    # cookies validen contra este backend.
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
        # Fase 9.8 (pentest MEDIA): fuera de development, SECRET_KEY debe estar
        # definida Y ser DISTINTA de admin_api_key. Con secret_key vacia,
        # admin_auth._signing_key cae en admin_api_key para firmar las cookies
        # de sesion -> quien filtre la admin key puede FORJAR sesiones offline
        # (confirmado en el pentest) sin pasar por /admin/login ni el rate
        # limiter. Separar la llave de firma de la credencial de acceso corta
        # ese vector.
        if not self.secret_key:
            missing.append("secret_key")
        elif self.secret_key == self.admin_api_key:
            missing.append("secret_key (debe ser DISTINTA de admin_api_key)")

        if missing:
            raise ValueError(
                f"Configuracion critica faltante para environment={self.environment!r}: "
                f"{', '.join(missing)}. Definila en .env o en las variables de entorno del deploy."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


class AIConfigError(RuntimeError):
    """ai_config.json ausente o malformado. Se lanza en vez de dejar propagar
    un JSONDecodeError/OSError crudo para que el manejador de turno pueda
    degradar con el mensaje de error del sistema en vez de un 500 (Fase 9.8/
    A5)."""


@lru_cache
def get_ai_config() -> dict:
    # A5: sin este try/except, un ai_config.json con un typo (el punto de
    # intervencion manual mas frecuente del proyecto) lanzaba un
    # JSONDecodeError crudo. Como get_ai_config esta bajo @lru_cache y es
    # lazy, no rompia el arranque sino la primera request que lo tocara, y en
    # varios call-sites eso queda FUERA del try/except del turno -> 500 crudo.
    try:
        with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise AIConfigError(f"No se pudo leer ai_config.json ({AI_CONFIG_PATH}): {exc}") from exc


def reload_ai_config() -> None:
    """Invalida el cache de get_ai_config para tomar cambios de ai_config.json
    sin reiniciar el proceso (Fase 9.8/C2). Lo expone POST /admin/config/reload.
    get_settings() NO se recarga aca a proposito -- las settings vienen de .env
    y variables de entorno del deploy, cambiarlas si requiere reinicio."""
    get_ai_config.cache_clear()
