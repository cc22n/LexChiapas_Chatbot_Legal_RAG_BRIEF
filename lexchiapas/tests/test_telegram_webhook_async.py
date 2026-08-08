"""Tests de regresion para los hallazgos A1 (idempotencia) y A2 (webhook no
debe bloquear la respuesta HTTP con el pipeline RAG completo) de la
auditoria de salud del backend (2026-08-06)."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.api import telegram_webhook
from app.main import app

SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def _configure_secret(monkeypatch):
    monkeypatch.setattr(telegram_webhook.settings, "telegram_webhook_secret", SECRET)


def _post_update(client: TestClient, update_id: int) -> "httpx.Response":  # noqa: F821
    return client.post(
        "/webhook/telegram",
        json={"update_id": update_id, "message": {"chat": {"id": 1}, "from": {"id": 1}, "text": "hola"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )


def test_webhook_rejects_wrong_secret():
    with TestClient(app) as client:
        response = client.post(
            "/webhook/telegram",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
    assert response.status_code == 401


def test_webhook_returns_ok_immediately_without_waiting_for_the_pipeline(monkeypatch):
    # BUG REAL corregido (hallazgo A2): antes, este endpoint esperaba a que
    # bot.handle_update() (pipeline RAG completo, hasta varios hops LLM)
    # terminara antes de responder. Este mock simula un pipeline lento --
    # si el fix de asyncio.create_task se revierte, este test tarda >=1s y
    # falla el assert de tiempo.
    pipeline_started = asyncio.Event()
    pipeline_finished = asyncio.Event()

    async def slow_handle_update(update: dict) -> None:
        pipeline_started.set()
        await asyncio.sleep(1.0)
        pipeline_finished.set()

    monkeypatch.setattr(telegram_webhook.bot, "handle_update", slow_handle_update)
    monkeypatch.setattr(telegram_webhook, "already_processed", lambda update_id: False)

    with TestClient(app) as client:
        start = time.monotonic()
        response = _post_update(client, update_id=999001)
        elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    # El endpoint debe responder MUCHO antes de que el mock de 1s termine.
    assert elapsed < 0.5


def test_webhook_deduplicates_by_update_id(monkeypatch):
    # BUG REAL corregido (hallazgo A1): un update_id repetido (reintento de
    # Telegram) no debe disparar el pipeline una segunda vez.
    call_count = 0

    async def counting_handle_update(update: dict) -> None:
        nonlocal call_count
        call_count += 1

    monkeypatch.setattr(telegram_webhook.bot, "handle_update", counting_handle_update)

    seen: set[int] = set()

    def fake_already_processed(update_id: int) -> bool:
        if update_id in seen:
            return True
        seen.add(update_id)
        return False

    monkeypatch.setattr(telegram_webhook, "already_processed", fake_already_processed)

    with TestClient(app) as client:
        first = _post_update(client, update_id=999002)
        second = _post_update(client, update_id=999002)  # mismo update_id -- reintento simulado
        # Le da tiempo al background task del primer POST a terminar antes
        # de revisar call_count (TestClient no espera background tasks).
        time.sleep(0.2)

    assert first.status_code == 200
    assert second.status_code == 200
    assert call_count == 1
