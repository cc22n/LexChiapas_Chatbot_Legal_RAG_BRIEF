from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, APITimeoutError, InternalServerError, RateLimitError

import app.workers.alerting_tasks as alerting


def _status_error(cls, status, body=None):
    request = httpx.Request("POST", "https://x/v1/chat/completions")
    response = httpx.Response(status, request=request)
    return cls(f"HTTP {status}", response=response, body=body)


class _Client:
    def __init__(self, error):
        self._error = error
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(choices=[])


def _setup(monkeypatch, entries, errors):
    """entries: lista de (provider, model[, temperature]); errors: {provider: excepcion | None}."""
    fallback = []
    for e in entries:
        item = {"provider": e[0], "model": e[1]}
        if len(e) > 2:
            item["temperature"] = e[2]
        fallback.append(item)
    monkeypatch.setattr(alerting, "get_ai_config", lambda: {"llm": {"temperature": 0.1, "fallback_order": fallback}})
    clients = {p: _Client(err) for p, err in errors.items()}
    monkeypatch.setattr(alerting, "get_client_for_provider", lambda provider, timeout=None: clients[provider])
    return clients


def test_all_models_healthy_produces_no_alert(monkeypatch):
    _setup(monkeypatch, [("openai", "a"), ("moonshot", "b")], {"openai": None, "moonshot": None})
    message, summary = alerting._check_llm_models()
    assert message is None and summary["problems"] == []


def test_model_retired_with_410_alerts_and_names_it(monkeypatch):
    # El caso real del 2026-10-22: tres modelos NIM devolvian HTTP 410 Gone.
    _setup(monkeypatch, [("nvidia_nim", "viejo"), ("openai", "bueno")],
           {"nvidia_nim": _status_error(APIStatusError, 410), "openai": None})
    message, summary = alerting._check_llm_models()
    assert "nvidia_nim/viejo" in message and "retirado" in message
    assert "Siguen respondiendo: openai/bueno" in message
    assert summary["problems"] == [("nvidia_nim/viejo", "gone")]


def test_404_counts_as_retired(monkeypatch):
    _setup(monkeypatch, [("nvidia_nim", "x")], {"nvidia_nim": _status_error(APIStatusError, 404)})
    message, _ = alerting._check_llm_models()
    assert "retirado" in message and "NINGUNA entrada respondio bien" in message


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_credentials_alert(monkeypatch, status):
    _setup(monkeypatch, [("openai", "a")], {"openai": _status_error(APIStatusError, status)})
    message, _ = alerting._check_llm_models()
    assert "credenciales rechazadas" in message


def test_exhausted_credit_alerts(monkeypatch):
    err = _status_error(RateLimitError, 429, body={"code": "insufficient_quota"})
    _setup(monkeypatch, [("openai", "a"), ("moonshot", "b")], {"openai": err, "moonshot": None})
    message, summary = alerting._check_llm_models()
    assert "credito agotado" in message and summary["problems"] == [("openai/a", "quota")]


@pytest.mark.parametrize(
    "error",
    [
        APITimeoutError(request=httpx.Request("POST", "https://x")),
        _status_error(InternalServerError, 503),
        _status_error(RateLimitError, 429, body={"code": "rate_limit_exceeded"}),
    ],
)
def test_transient_failures_do_not_alert(monkeypatch, error):
    # Timeouts, 5xx y 429 por ritmo son ruido con proveedores intermitentes.
    _setup(monkeypatch, [("nvidia_nim", "a")], {"nvidia_nim": error})
    message, summary = alerting._check_llm_models()
    assert message is None and summary["transient"] == ["nvidia_nim/a"]


def test_probe_uses_the_entry_temperature_override(monkeypatch):
    # Kimi solo acepta temperature=1: sin el override la sonda daria 400 y
    # parecería un fallo permanente que no es.
    clients = _setup(monkeypatch, [("moonshot", "kimi", 1), ("openai", "gpt")], {"moonshot": None, "openai": None})
    alerting._check_llm_models()
    assert clients["moonshot"].calls[0]["temperature"] == 1
    assert clients["openai"].calls[0]["temperature"] == 0.1
    assert clients["openai"].calls[0]["max_tokens"] == 16


def test_canary_sends_once_and_respects_cooldown(monkeypatch):
    _setup(monkeypatch, [("nvidia_nim", "viejo")], {"nvidia_nim": _status_error(APIStatusError, 410)})
    sent = []
    monkeypatch.setattr(alerting, "send_admin_telegram_alert", lambda text: sent.append(text) or True)
    allowed = iter([True, False])
    monkeypatch.setattr(alerting, "_cooldown_allows", lambda kind: next(allowed))
    first = alerting.llm_models_canary.run()
    second = alerting.llm_models_canary.run()
    assert first["sent"] is True and second["sent"] is False
    assert len(sent) == 1


def test_canary_never_raises_even_if_the_check_explodes(monkeypatch):
    monkeypatch.setattr(alerting, "_check_llm_models", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert alerting.llm_models_canary.run() == {"problems": [], "sent": False}
