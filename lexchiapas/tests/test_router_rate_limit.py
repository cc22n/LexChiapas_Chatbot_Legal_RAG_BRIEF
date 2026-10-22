import httpx
import pytest
from openai import RateLimitError

from app.llm import router


def _rate_limit_error(retry_after: str | None = None) -> RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(429, headers=headers, request=httpx.Request("POST", "http://x"))
    return RateLimitError("429", response=response, body=None)


class _Completions:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        class _Msg:
            content = outcome

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]
            usage = None

        return _Resp()


def _setup(monkeypatch, clients):
    config = {
        "llm": {
            "fallback_order": [
                {"provider": "nvidia_nim", "model": "a"},
                {"provider": "nvidia_nim", "model": "b"},
                {"provider": "openai", "model": "c"},
            ]
        }
    }
    monkeypatch.setattr(router, "get_ai_config", lambda: config)

    class _Client:
        def __init__(self, completions):
            self.chat = type("Chat", (), {"completions": completions})()

    monkeypatch.setattr(router, "get_client_for_provider", lambda provider, timeout=None: _Client(clients[provider]))
    sleeps = []
    monkeypatch.setattr(router.time, "sleep", sleeps.append)
    return sleeps


def test_429_retries_same_model_once_after_backoff(monkeypatch):
    nim = _Completions([_rate_limit_error(retry_after="2"), "respuesta"])
    openai_ = _Completions([])
    sleeps = _setup(monkeypatch, {"nvidia_nim": nim, "openai": openai_})

    text, model, _, _ = router.generate_with_fallback([{"role": "user", "content": "hola"}])

    assert (text, model) == ("respuesta", "a")
    assert sleeps == [2.0]
    assert openai_.calls == 0


def test_persistent_429_skips_rest_of_provider_and_falls_to_next(monkeypatch):
    nim = _Completions([_rate_limit_error(), _rate_limit_error()])
    openai_ = _Completions(["desde openai"])
    sleeps = _setup(monkeypatch, {"nvidia_nim": nim, "openai": openai_})

    text, model, _, _ = router.generate_with_fallback([{"role": "user", "content": "hola"}])

    assert (text, model) == ("desde openai", "c")
    assert nim.calls == 2  # modelo "b" de NIM no se intenta
    assert sleeps == [router.RATE_LIMIT_DEFAULT_BACKOFF_SECONDS]


def test_backoff_is_capped(monkeypatch):
    nim = _Completions([_rate_limit_error(retry_after="120"), "ok"])
    sleeps = _setup(monkeypatch, {"nvidia_nim": nim, "openai": _Completions([])})

    router.generate_with_fallback([{"role": "user", "content": "hola"}])

    assert sleeps == [router.RATE_LIMIT_MAX_BACKOFF_SECONDS]


def test_all_providers_failing_still_raises(monkeypatch):
    nim = _Completions([_rate_limit_error(), _rate_limit_error()])
    openai_ = _Completions([RuntimeError("boom")])
    _setup(monkeypatch, {"nvidia_nim": nim, "openai": openai_})

    with pytest.raises(router.AllModelsFailedError):
        router.generate_with_fallback([{"role": "user", "content": "hola"}])
