import asyncio

from fastapi import HTTPException
from telegram import Bot

from app.api.rate_limit import enforce_rate_limit
from app.bots.base_bot import BaseBot
from app.bots.conversation_store import handle_turn
from app.bots.output_formatter import clean_markdown
from app.config import get_settings
from app.database import SessionLocal
from app.models import Document
from app.rag.guardrails import GREETING_RESPONSE

# Reusa GREETING_RESPONSE (app.rag.guardrails) en vez de tener su propio
# texto -- antes este mensaje y la respuesta que recibia un "hola" escrito a
# mano dentro del chat podian divergir con el tiempo (dos fuentes de verdad
# del mismo saludo). Solo se le agrega el hint de /ayuda, especifico de
# Telegram (no aplica al chat web, que no tiene comandos slash).
WELCOME_MESSAGE = GREETING_RESPONSE + "\n\nUsa /ayuda para ver los comandos disponibles."

HELP_MESSAGE = (
    "Comandos:\n"
    "/start - mensaje de bienvenida\n"
    "/ayuda - este mensaje\n"
    "/areas - areas del derecho que cubro\n\n"
    "O simplemente escribe tu pregunta sobre una ley de Chiapas."
)

NO_AREAS_MESSAGE = "Todavia no tengo leyes cargadas. Vuelve pronto."

RATE_LIMIT_MESSAGE = (
    "Estas preguntando muy seguido. Dame un momento y vuelve a intentar en "
    "un minuto -- asi le dejo lugar a los demas usuarios (el cupo gratis de "
    "NVIDIA NIM se comparte entre todos)."
)


def build_areas_message(db) -> str:
    """Lista las areas del derecho y leyes activas reales, en vez del
    placeholder original ("Areas del derecho disponibles: en
    configuracion."). Consulta documents.area_derecho directo -- si se
    carga una ley nueva (Fase 1/2: ingest_document), el comando la refleja
    sin tocar este archivo.
    """
    rows = (
        db.query(Document.area_derecho, Document.nombre)
        .filter(Document.is_active.is_(True))
        .order_by(Document.area_derecho, Document.nombre)
        .all()
    )
    if not rows:
        return NO_AREAS_MESSAGE

    areas: dict[str, list[str]] = {}
    for area, nombre in rows:
        areas.setdefault(area or "sin clasificar", []).append(nombre)

    lines = ["Areas del derecho que cubro actualmente:"]
    for area in sorted(areas):
        lines.append(f"\n{area.replace('_', ' ').capitalize()}:")
        for nombre in areas[area]:
            lines.append(f"  - {nombre}")
    return "\n".join(lines)


class TelegramBot(BaseBot):
    platform = "telegram"

    def __init__(self) -> None:
        settings = get_settings()
        self._bot = Bot(token=settings.telegram_bot_token) if settings.telegram_bot_token else None

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message or "text" not in message:
            return

        chat_id = str(message["chat"]["id"])
        user_id = str(message["from"]["id"])
        text = message["text"]

        if text.startswith("/start"):
            await self.send_message(chat_id, WELCOME_MESSAGE)
            return
        if text.startswith("/ayuda"):
            await self.send_message(chat_id, HELP_MESSAGE)
            return
        if text.startswith("/areas"):
            # BUG REAL (auditoria de calidad de codigo, 2026-08-06): esta
            # query (y, mas abajo, el pipeline RAG completo de
            # handle_message) es 100% sincrona -- sin asyncio.to_thread,
            # bloqueaba el unico hilo del event loop de uvicorn mientras
            # corria, congelando TODAS las requests concurrentes del
            # proceso (otros usuarios de Telegram, health checks, el
            # dashboard admin). app/api/chat_web.py no tiene este problema
            # porque su endpoint es `def`, no `async def` -- FastAPI lo
            # despacha solo a su threadpool.
            message_text = await asyncio.to_thread(self._build_areas_message_sync)
            await self.send_message(chat_id, message_text)
            return

        answer = await self.handle_message(user_id, chat_id, text)
        await self.send_message(chat_id, answer)

    async def handle_message(self, user_id: str, chat_id: str, text: str) -> str:
        # Rate limit por chat_id (no user_id): en un chat privado ambos
        # coinciden, pero chat_id es la clave que ya se usa para persistir
        # la Conversation -- mantiene el mismo criterio de "canal activo" en
        # todo el bot. enforce_rate_limit() esta pensada para levantarse
        # como HTTPException en un endpoint FastAPI (la usa tambien
        # app/api/chat_web.py); aqui no hay una respuesta HTTP que el
        # usuario vea directo, asi que se atrapa y se responde por Telegram
        # en vez de dejar que la excepcion suba y rompa handle_update()
        # (eso evitaria que el webhook devuelva 200 a tiempo, y Telegram
        # reintentaria mandando el mismo update).
        try:
            enforce_rate_limit(chat_id)
        except HTTPException:
            return RATE_LIMIT_MESSAGE

        # El pipeline RAG completo (queries SQLAlchemy sync, embeddings y
        # generacion via cliente OpenAI sync con hasta 60s de timeout por
        # hop, reranker via httpx sync) corre en un thread aparte -- ver
        # comentario BUG REAL en handle_update sobre por que esto importa.
        return await asyncio.to_thread(self._handle_message_sync, user_id, chat_id, text)

    def _handle_message_sync(self, user_id: str, chat_id: str, text: str) -> str:
        db = SessionLocal()
        try:
            response, _ = handle_turn(db, self.platform, user_id, chat_id, text)
            return response.answer
        finally:
            db.close()

    @staticmethod
    def _build_areas_message_sync() -> str:
        db = SessionLocal()
        try:
            return build_areas_message(db)
        finally:
            db.close()

    async def send_message(self, chat_id: str, text: str) -> None:
        if self._bot is None:
            raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado")
        # Capa 2 (backend) de Fase 3.5: garantiza texto plano sin importar
        # si el LLM siguio la instruccion de formato del system prompt.
        await self._bot.send_message(chat_id=chat_id, text=clean_markdown(text))
