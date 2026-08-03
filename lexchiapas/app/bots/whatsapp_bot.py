from app.bots.base_bot import BaseBot

# Fase 5 del brief. Debe implementar BaseBot igual que TelegramBot y reusar
# app/rag/rag_pipeline.py sin duplicar logica de RAG aqui.


class WhatsAppBot(BaseBot):
    platform = "whatsapp"

    async def handle_message(self, user_id: str, chat_id: str, text: str) -> str:
        raise NotImplementedError("WhatsAppBot: fase 5 del proyecto, no implementado todavia")

    async def send_message(self, chat_id: str, text: str) -> None:
        raise NotImplementedError("WhatsAppBot: fase 5 del proyecto, no implementado todavia")
