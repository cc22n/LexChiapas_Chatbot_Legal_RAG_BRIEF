"""Registra el webhook de Telegram con su secret_token (Fase 9.8/A14).

El receptor POST /webhook/telegram (app/api/telegram_webhook.py) es
fail-closed: exige el header X-Telegram-Bot-Api-Secret-Token igual a
settings.telegram_webhook_secret, o rechaza 401. Telegram solo manda ese
header si el webhook se registro con `secret_token`. Sin este paso, TODOS los
updates se rechazan en silencio -- por eso hace falta correr esto una vez tras
el deploy (o cada vez que cambie la URL publica o el secret).

Uso:
    python scripts/set_telegram_webhook.py https://tu-dominio.com/webhook/telegram

Toma el token del bot y el secret de las settings (.env: TELEGRAM_BOT_TOKEN,
TELEGRAM_WEBHOOK_SECRET). La URL publica del webhook se pasa como argumento, o
via la variable de entorno TELEGRAM_WEBHOOK_URL. Seguro para re-correr.
"""

import os
import sys

import httpx

# Permite `python scripts/set_telegram_webhook.py` desde la raiz del backend.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    token = settings.telegram_bot_token
    secret = settings.telegram_webhook_secret

    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TELEGRAM_WEBHOOK_URL", "")

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN no esta configurado en .env", file=sys.stderr)
        return 1
    if not secret:
        print(
            "ERROR: TELEGRAM_WEBHOOK_SECRET no esta configurado en .env -- el endpoint "
            "es fail-closed y rechazaria todo sin el.",
            file=sys.stderr,
        )
        return 1
    if not url:
        print(
            "ERROR: falta la URL publica del webhook.\n"
            "  Uso: python scripts/set_telegram_webhook.py https://tu-dominio.com/webhook/telegram\n"
            "  (o exporta TELEGRAM_WEBHOOK_URL)",
            file=sys.stderr,
        )
        return 1

    resp = httpx.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={
            "url": url,
            "secret_token": secret,
            # allowed_updates acotado a mensajes: este bot solo procesa texto
            # entrante, no callbacks/inline queries.
            "allowed_updates": ["message"],
        },
        timeout=15,
    )
    print(f"HTTP {resp.status_code}: {resp.text}")
    # Telegram responde {"ok": true, ...} en exito.
    try:
        ok = resp.json().get("ok", False)
    except Exception:  # noqa: BLE001
        ok = False
    if ok:
        print(f"Webhook registrado en: {url}")
        return 0
    print("El registro NO fue exitoso -- revisa el mensaje de Telegram arriba.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
