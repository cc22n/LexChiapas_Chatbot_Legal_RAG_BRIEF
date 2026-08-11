import asyncio
import logging

from telegram import Bot

from app.bots.telegram_bot import TelegramBot
from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_polling() -> None:
    """Modo de prueba local: pregunta a Telegram por mensajes nuevos en vez
    de recibirlos por webhook. Evita necesitar un endpoint HTTPS publico
    (ngrok, etc.) mientras se prueba en la maquina local. Para produccion,
    usar el webhook real (app/api/telegram_webhook.py).
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado en .env")

    raw_bot = Bot(token=settings.telegram_bot_token)
    bot = TelegramBot()

    await raw_bot.delete_webhook(drop_pending_updates=True)
    me = await raw_bot.get_me()
    logger.info("Polling iniciado como @%s -- Ctrl+C para detener", me.username)

    offset = None
    while True:
        # BUG REAL (2026-08-10, encontrado al dejar esto corriendo para
        # grabar un demo): get_updates en si mismo puede tirar TimedOut/
        # NetworkError por un hipo transitorio de red -- antes esto no
        # tenia try/except propio (solo bot.handle_update mas abajo lo
        # tenia), asi que un solo timeout tumbaba TODO el script de
        # polling, no solo ese ciclo. Mismo criterio que el resto del
        # proyecto con fallas de red intermitentes: loguear y seguir, no
        # morir por un hipo de una llamada auxiliar.
        try:
            updates = await raw_bot.get_updates(offset=offset, timeout=30)
        except Exception:
            logger.exception("get_updates fallo, reintentando")
            continue

        for update in updates:
            offset = update.update_id + 1
            try:
                await bot.handle_update(update.to_dict())
            except Exception:
                logger.exception("Error procesando update %s", update.update_id)


if __name__ == "__main__":
    asyncio.run(run_polling())
