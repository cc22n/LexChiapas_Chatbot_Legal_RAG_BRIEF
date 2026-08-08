"""Tests de get_or_create_conversation contra una Session fake (sin DB real)
-- ejercitan el CONTROL FLOW del fix de la race condition (auditoria de
base de datos, 2026-08-06), no la constraint real de Postgres (esa ya se
prueba indirectamente: el UniqueConstraint es lo que produce el
IntegrityError real que este codigo debe atrapar)."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.bots.conversation_store import get_or_create_conversation
from app.models import Conversation


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter_by(self, **kwargs):
        return self

    def one_or_none(self):
        return self._result

    def one(self):
        return self._result


class _FakeSession:
    """Primera llamada a query() simula el SELECT inicial (nadie encontro
    la conversation todavia); llamadas siguientes simulan el re-SELECT
    posterior al rollback, devolviendo `winner`."""

    def __init__(self, winner=None, commit_raises: bool = False):
        self._winner = winner
        self._commit_raises = commit_raises
        self._query_call_count = 0
        self.added = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.refresh_calls = 0

    def query(self, model):
        self._query_call_count += 1
        if self._query_call_count == 1:
            return _FakeQuery(None)
        return _FakeQuery(self._winner)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_calls += 1
        if self._commit_raises:
            raise IntegrityError("insert into conversations ...", {}, Exception("duplicate key"))

    def rollback(self):
        self.rollback_calls += 1

    def refresh(self, obj):
        self.refresh_calls += 1


def test_creates_conversation_when_none_exists():
    db = _FakeSession(commit_raises=False)

    result = get_or_create_conversation(db, "telegram", "user-1", "chat-1")

    assert result in db.added
    assert db.commit_calls == 1
    assert db.rollback_calls == 0
    assert db.refresh_calls == 1


def test_retries_and_returns_winner_after_concurrent_insert_wins_the_race():
    # BUG REAL corregido 2026-08-06: dos requests concurrentes para el mismo
    # (platform, chat_id) -- por ejemplo un reintento de webhook de
    # Telegram -- podian ambas ver None en el SELECT inicial e intentar
    # insertar, creando conversaciones duplicadas. Con el
    # UniqueConstraint(platform, chat_id) real, el segundo commit() truena
    # con IntegrityError -- este test verifica que get_or_create_conversation
    # atrapa ese error, hace rollback de su propio insert perdedor, y relee
    # la fila que SI gano la carrera en vez de propagar el error.
    winner = Conversation(id=42, platform="telegram", user_id="user-1", chat_id="chat-1")
    db = _FakeSession(winner=winner, commit_raises=True)

    result = get_or_create_conversation(db, "telegram", "user-1", "chat-1")

    assert result is winner
    assert db.commit_calls == 1
    assert db.rollback_calls == 1
    # No se debe refrescar el insert perdedor -- fue descartado por el
    # rollback, refresh() sobre un objeto que ya no existe en la sesion
    # tronaria.
    assert db.refresh_calls == 0


def test_returns_existing_conversation_without_touching_commit():
    existing = Conversation(id=7, platform="telegram", user_id="user-1", chat_id="chat-1")

    class _FoundSession(_FakeSession):
        def query(self, model):
            return _FakeQuery(existing)

    db = _FoundSession()

    result = get_or_create_conversation(db, "telegram", "user-1", "chat-1")

    assert result is existing
    assert db.commit_calls == 0
    assert db.rollback_calls == 0
