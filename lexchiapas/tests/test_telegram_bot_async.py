"""Test de regresion para el bug de event loop bloqueado corregido en
app.bots.telegram_bot (auditoria de calidad de codigo, 2026-08-06):
TelegramBot.handle_message es `async def` pero antes corria su cuerpo
(DB + pipeline RAG, todo sincrono) directo en el event loop en vez de en un
thread aparte -- una sola request lenta congelaba TODAS las requests
concurrentes del proceso. Ahora usa asyncio.to_thread."""

import asyncio
import time

import pytest

from app.api import rate_limit
from app.bots.telegram_bot import TelegramBot


@pytest.fixture(autouse=True)
def _clean_rate_limit_state():
    rate_limit._requests_by_session.clear()
    yield
    rate_limit._requests_by_session.clear()


@pytest.mark.asyncio
async def test_handle_message_does_not_block_the_event_loop(monkeypatch):
    bot = TelegramBot()

    def slow_blocking_pipeline(user_id: str, chat_id: str, text: str) -> str:
        time.sleep(0.3)  # simula el pipeline RAG sincrono (DB + LLM real)
        return "respuesta simulada"

    monkeypatch.setattr(bot, "_handle_message_sync", slow_blocking_pipeline)

    tick_count = 0

    async def ticker():
        nonlocal tick_count
        while True:
            await asyncio.sleep(0.02)
            tick_count += 1

    ticker_task = asyncio.create_task(ticker())
    try:
        result = await bot.handle_message("user-1", "chat-async-test", "una pregunta")
    finally:
        ticker_task.cancel()

    assert result == "respuesta simulada"
    # Si handle_message bloqueara el event loop (BUG REAL corregido), el
    # ticker no habria podido correr NINGUNA vez durante esos 0.3s -- con
    # asyncio.to_thread, el loop queda libre y el ticker avanza varias veces
    # mientras el thread "trabaja". Umbral bajo (3, no ~15) para no ser
    # fragil ante jitter del scheduler en CI.
    assert tick_count >= 3


@pytest.mark.asyncio
async def test_handle_message_returns_rate_limit_message_without_touching_thread(monkeypatch):
    bot = TelegramBot()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("_handle_message_sync no deberia llamarse si el rate limit ya rechazo")

    monkeypatch.setattr(bot, "_handle_message_sync", fail_if_called)

    for _ in range(rate_limit.MAX_REQUESTS_PER_WINDOW):
        rate_limit.enforce_rate_limit("chat-rate-limited")

    result = await bot.handle_message("user-1", "chat-rate-limited", "otra pregunta")

    from app.bots.telegram_bot import RATE_LIMIT_MESSAGE

    assert result == RATE_LIMIT_MESSAGE
