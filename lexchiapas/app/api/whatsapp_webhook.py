from fastapi import APIRouter, Request

router = APIRouter(tags=["whatsapp"])

# Fase 5 del brief: implementar cuando se integre WhatsAppBot (OpenWA/Baileys).
# Debe verificar la firma/token del proveedor antes de procesar, igual que
# telegram_webhook.py, antes de quedar activo en produccion.


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request) -> dict:
    raise NotImplementedError("WhatsApp bot: fase 5 del proyecto, no implementado todavia")
