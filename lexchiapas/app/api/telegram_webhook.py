import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.bots.telegram_bot import TelegramBot
from app.config import get_settings

router = APIRouter(tags=["telegram"])
settings = get_settings()
bot = TelegramBot()
logger = logging.getLogger("lexchiapas.telegram_webhook")

if not settings.telegram_webhook_secret:
    logger.warning(
        "TELEGRAM_WEBHOOK_SECRET no esta configurado -- /webhook/telegram "
        "rechazara TODAS las requests hasta que se configure (fail-closed). "
        "BUG REAL corregido (2026-08-04): antes, sin este secreto "
        "configurado, el endpoint aceptaba CUALQUIER POST sin autenticar en "
        "silencio -- un despliegue con esta variable olvidada quedaba "
        "abierto a cualquiera que encontrara la URL, sin ningun warning."
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
    await bot.handle_update(update)
    return {"ok": True}
