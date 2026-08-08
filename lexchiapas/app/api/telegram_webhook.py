import asyncio
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.bots.telegram_bot import TelegramBot
from app.bots.telegram_dedup import already_processed
from app.config import get_settings

router = APIRouter(tags=["telegram"])
settings = get_settings()
bot = TelegramBot()
logger = logging.getLogger("lexchiapas.telegram_webhook")

# Referencias fuertes a los Tasks de background mientras corren (patron
# estandar de asyncio.create_task: sin esto, el garbage collector puede
# recolectar un Task "fire-and-forget" a mitad de camino porque nada mas lo
# referencia). Se limpia solo via el done_callback de mas abajo.
_background_tasks: set[asyncio.Task] = set()

if not settings.telegram_webhook_secret:
    logger.warning(
        "TELEGRAM_WEBHOOK_SECRET no esta configurado -- /webhook/telegram "
        "rechazara TODAS las requests hasta que se configure (fail-closed). "
        "BUG REAL corregido (2026-08-04): antes, sin este secreto "
        "configurado, el endpoint aceptaba CUALQUIER POST sin autenticar en "
        "silencio -- un despliegue con esta variable olvidada quedaba "
        "abierto a cualquiera que encontrara la URL, sin ningun warning."
    )


async def _process_update_safely(update: dict) -> None:
    """Envoltorio del procesamiento real -- ver telegram_webhook() de abajo
    sobre por que esto corre como background task sin que nadie lo espere.

    Sin este try/except, una excepcion real (NVIDIA caido, bug de codigo)
    se perderia en el manejador de excepciones por default de asyncio (solo
    imprime a stderr sin el contexto del update) en vez de quedar en el log
    real de la app con el update_id para poder diagnosticar despues.
    """
    try:
        await bot.handle_update(update)
    except Exception:
        logger.exception(
            "Error procesando update de Telegram (update_id=%s)", update.get("update_id")
        )


@router.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    # Fail-closed: sin secreto configurado, no hay forma de verificar que la
    # request viene de verdad de Telegram, asi que se rechaza en vez de
    # aceptar en silencio (ver warning de startup arriba).
    if not settings.telegram_webhook_secret or not hmac.compare_digest(
        x_telegram_bot_api_secret_token or "", settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=401, detail="invalid secret token")

    update = await request.json()
    update_id = update.get("update_id")

    # BUG REAL corregido (auditoria de salud del backend, 2026-08-06,
    # hallazgo A1): ver docstring de already_processed. update_id puede
    # faltar en payloads sinteticos/de prueba -- en ese caso no se puede
    # deduplicar, se procesa igual (mismo criterio permisivo que el resto de
    # esta funcion ante datos incompletos).
    if update_id is not None and already_processed(update_id):
        return {"ok": True}

    # BUG REAL corregido (hallazgo A2): antes, `await bot.handle_update(...)`
    # corria el pipeline RAG completo (embeddings + busqueda + generacion,
    # hasta varios hops LLM con timeout de 60s cada uno en la ruta agentica)
    # DENTRO de la respuesta HTTP de este webhook. Un caso lento realista
    # supera comodamente los ~60s que Telegram tolera antes de reintentar la
    # entrega -- lo cual, sin el fix de A1 arriba, generaba un reproceso
    # duplicado en cascada. Ahora se responde 200 de inmediato (Telegram no
    # necesita el resultado del pipeline en la respuesta del webhook, la
    # respuesta real se manda por separado via bot.send_message dentro de
    # handle_update) y el turno se procesa en background.
    task = asyncio.create_task(_process_update_safely(update))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"ok": True}
