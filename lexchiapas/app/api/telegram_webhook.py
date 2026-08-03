from fastapi import APIRouter, Header, HTTPException, Request

from app.bots.telegram_bot import TelegramBot
from app.config import get_settings

router = APIRouter(tags=["telegram"])
settings = get_settings()
bot = TelegramBot()


@router.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=401, detail="invalid secret token")

    update = await request.json()
    await bot.handle_update(update)
    return {"ok": True}
