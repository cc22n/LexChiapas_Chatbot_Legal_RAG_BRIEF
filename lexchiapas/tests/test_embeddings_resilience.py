"""Resiliencia de embeddings y config (Fase 9.8, hallazgos C2/A5).

Regresion del incidente real del 2026-08-25: nvidia/nv-embedqa-e5-v5 llego a
su fin de vida y respondio 410 Gone; embed_text no lo distinguia del ruido
transitorio y no habia log accionable, asi que la caida tardo ~2 dias en
detectarse. Estos tests fijan que:
  - un 404/410 emite el marcador EMBEDDING_MODEL_DEAD y re-lanza (sin retry),
  - un 4xx distinto propaga SIN el marcador (no es "modelo muerto"),
  - un ai_config.json malformado lanza AIConfigError (no un crudo).
"""

import json
import logging

import httpx
import pytest
from openai import APIStatusError

import app.config as config
import app.llm.providers as providers
from app.llm.providers import EMBEDDING_MODEL_DEAD_MARKER, embed_text


class _FakeEmbeddings:
    def __init__(self, exc):
        self._exc = exc

    def create(self, *args, **kwargs):
        raise self._exc


class _FakeClient:
    def __init__(self, exc):
        self.embeddings = _FakeEmbeddings(exc)


def _api_status_error(status_code: int) -> APIStatusError:
    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/embeddings")
    response = httpx.Response(status_code, request=request)
    return APIStatusError(f"HTTP {status_code}", response=response, body=None)


@pytest.mark.parametrize("status_code", [404, 410])
def test_embed_text_model_dead_logs_marker_and_raises(monkeypatch, caplog, status_code):
    monkeypatch.setattr(providers, "get_nim_client", lambda: _FakeClient(_api_status_error(status_code)))
    with caplog.at_level(logging.ERROR, logger="lexchiapas.llm.providers"):
        with pytest.raises(APIStatusError):
            embed_text("cualquier pregunta")
    assert EMBEDDING_MODEL_DEAD_MARKER in caplog.text


def test_embed_text_other_4xx_propagates_without_marker(monkeypatch, caplog):
    # 400 (ej. input invalido) NO es "modelo muerto": debe propagar sin el
    # marcador, para que la alerta no se dispare por un error de payload.
    monkeypatch.setattr(providers, "get_nim_client", lambda: _FakeClient(_api_status_error(400)))
    with caplog.at_level(logging.ERROR, logger="lexchiapas.llm.providers"):
        with pytest.raises(APIStatusError):
            embed_text("cualquier pregunta")
    assert EMBEDDING_MODEL_DEAD_MARKER not in caplog.text


def test_get_ai_config_malformed_raises_aiconfigerror(monkeypatch, tmp_path):
    bad = tmp_path / "ai_config.json"
    bad.write_text("{ esto no es json valido ", encoding="utf-8")
    monkeypatch.setattr(config, "AI_CONFIG_PATH", bad)
    config.get_ai_config.cache_clear()
    try:
        with pytest.raises(config.AIConfigError):
            config.get_ai_config()
    finally:
        config.get_ai_config.cache_clear()  # no contaminar el cache para otros tests
