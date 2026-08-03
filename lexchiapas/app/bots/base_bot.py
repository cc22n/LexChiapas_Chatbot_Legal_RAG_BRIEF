from abc import ABC, abstractmethod


class BaseBot(ABC):
    """Interfaz comun para todos los canales (Telegram, WhatsApp, ...).

    La logica de RAG vive fuera de aqui (app/rag/rag_pipeline.py); cada bot
    solo traduce el formato de su plataforma hacia/desde esa logica comun.
    """

    platform: str

    @abstractmethod
    async def handle_message(self, user_id: str, chat_id: str, text: str) -> str:
        """Procesa un mensaje entrante y devuelve el texto de la respuesta."""

    @abstractmethod
    async def send_message(self, chat_id: str, text: str) -> None:
        """Envia un mensaje de vuelta al usuario en su plataforma."""
