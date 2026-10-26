from types import SimpleNamespace

import pytest

from app.llm import router


def _resp(content, finish_reason="stop", prompt=10, completion=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


class _Provider:
    def __init__(self, responses):
        self._responses = list(responses)
        self.max_tokens_seen = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.max_tokens_seen.append(kwargs["max_tokens"])
        return self._responses.pop(0)


def _setup(monkeypatch, entries, providers, retry=3072, base=1024):
    config = {"llm": {"max_tokens": base, "max_tokens_retry": retry, "fallback_order": entries}}
    monkeypatch.setattr(router, "get_ai_config", lambda: config)
    monkeypatch.setattr(router, "get_client_for_provider", lambda provider, timeout=None: providers[provider])
    usage = []
    monkeypatch.setattr(router, "record_usage", lambda p, c: usage.append((p, c)))
    return usage


MSG = [{"role": "user", "content": "hola"}]


def test_complete_answer_makes_a_single_call(monkeypatch):
    p = _Provider([_resp("Respuesta completa.")])
    _setup(monkeypatch, [{"provider": "a", "model": "m"}], {"a": p})
    text, model, _, _ = router.generate_with_fallback(MSG)
    assert (text, model) == ("Respuesta completa.", "m") and p.max_tokens_seen == [1024]


def test_truncated_answer_is_retried_with_a_bigger_budget_on_the_same_model(monkeypatch):
    p = _Provider([_resp("Corta porque la Suprema Corte de", "length"), _resp("Respuesta completa.", "stop", completion=40)])
    usage = _setup(monkeypatch, [{"provider": "a", "model": "m"}], {"a": p})
    text, model, _, completion = router.generate_with_fallback(MSG)
    assert text == "Respuesta completa." and model == "m" and completion == 40
    assert p.max_tokens_seen == [1024, 3072]
    assert len(usage) == 2  # los tokens del intento cortado tambien se pagaron y se contabilizan


def test_empty_content_with_length_is_retried(monkeypatch):
    # Razonamiento oculto: el tope se gasto pensando y no quedo texto.
    p = _Provider([_resp("", "length"), _resp("Ya con texto.")])
    _setup(monkeypatch, [{"provider": "a", "model": "kimi"}], {"a": p})
    assert router.generate_with_fallback(MSG)[0] == "Ya con texto."


def test_truncated_on_both_budgets_falls_to_the_next_model(monkeypatch):
    a = _Provider([_resp("cortada", "length"), _resp("cortada otra vez", "length")])
    b = _Provider([_resp("Completa del segundo modelo.")])
    _setup(monkeypatch, [{"provider": "a", "model": "m1"}, {"provider": "b", "model": "m2"}], {"a": a, "b": b})
    text, model, _, _ = router.generate_with_fallback(MSG)
    assert (text, model) == ("Completa del segundo modelo.", "m2") and a.max_tokens_seen == [1024, 3072]


def test_all_models_truncated_returns_longest_trimmed_to_last_sentence(monkeypatch):
    a = _Provider([_resp("Corta.", "length"), _resp("Corta.", "length")])
    b = _Provider([_resp("Primera frase completa. Segunda frase que se cort", "length"), _resp("Primera frase completa. Segunda frase que se cort", "length")])
    _setup(monkeypatch, [{"provider": "a", "model": "m1"}, {"provider": "b", "model": "m2"}], {"a": a, "b": b})
    text, model, _, _ = router.generate_with_fallback(MSG)
    assert text == "Primera frase completa." and model == "m2"  # no lanza y no entrega media frase


def test_entry_max_tokens_overrides_the_global_budget(monkeypatch):
    p = _Provider([_resp("ok")])
    _setup(monkeypatch, [{"provider": "a", "model": "m", "max_tokens": 2000}], {"a": p}, retry=3072)
    router.generate_with_fallback(MSG)
    assert p.max_tokens_seen == [2000]


def test_no_retry_when_retry_budget_is_not_larger(monkeypatch):
    p = _Provider([_resp("cortada", "length")])
    _setup(monkeypatch, [{"provider": "a", "model": "m"}], {"a": p}, retry=1024, base=1024)
    text, _, _, _ = router.generate_with_fallback(MSG)
    assert p.max_tokens_seen == [1024]  # un solo intento: no hay presupuesto mayor que probar


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Primera frase. Segunda incompl", "Primera frase."),
        ("Segun el Art. 22 de la ley, la jornada es de ocho horas. Ademas existe un caso espe", "Segun el Art. 22 de la ley, la jornada es de ocho horas."),
        ("Segun el Art. 22 de la", "Segun el Art. 22 de la"),  # solo hay una abreviatura: no hay frase completa que conservar
        ("Sin cierre de frase", "Sin cierre de frase"),
        ("", ""),
        (None, ""),
    ],
)
def test_trim_to_last_sentence(raw, expected):
    assert router._trim_to_last_sentence(raw) == expected
