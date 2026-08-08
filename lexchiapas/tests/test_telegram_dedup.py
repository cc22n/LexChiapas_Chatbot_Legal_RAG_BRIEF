"""Tests de regresion contra Redis real (sin mocks -- mismo criterio que
otros modulos que ya usan Redis en este proyecto) para el bug de
idempotencia corregido en el webhook de Telegram (auditoria de salud del
backend, 2026-08-06, hallazgo A1)."""

import uuid

from app.bots import telegram_dedup


def _unique_update_id() -> int:
    # int aleatorio grande, no un update_id real de Telegram -- solo hace
    # falta que sea unico entre corridas de test para no pisar keys viejas
    # en el Redis real compartido.
    return uuid.uuid4().int % (2**31)


def test_first_call_is_not_a_duplicate():
    update_id = _unique_update_id()
    assert telegram_dedup.already_processed(update_id) is False


def test_second_call_with_same_update_id_is_a_duplicate():
    update_id = _unique_update_id()
    assert telegram_dedup.already_processed(update_id) is False
    assert telegram_dedup.already_processed(update_id) is True
    # Una tercera vez sigue siendo duplicado -- la key no se borra al leerla.
    assert telegram_dedup.already_processed(update_id) is True


def test_different_update_ids_are_independent():
    first = _unique_update_id()
    second = _unique_update_id()
    assert telegram_dedup.already_processed(first) is False
    assert telegram_dedup.already_processed(second) is False
    assert telegram_dedup.already_processed(first) is True
    assert telegram_dedup.already_processed(second) is True


def test_fails_open_when_redis_is_unavailable(monkeypatch):
    # BUG REAL corregido: si Redis esta caido, no debe bloquear el
    # procesamiento de mensajes de Telegram -- se asume "no visto" (False)
    # en vez de propagar la excepcion, mismo criterio que app.rag.memory.
    class _BrokenRedis:
        def set(self, *args, **kwargs):
            raise ConnectionError("simulado: Redis no disponible")

    monkeypatch.setattr(telegram_dedup, "_get_redis_client", lambda: _BrokenRedis())

    assert telegram_dedup.already_processed(_unique_update_id()) is False
