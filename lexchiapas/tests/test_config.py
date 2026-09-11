"""Test de regresion para el hallazgo M4 de la auditoria de salud del
backend (2026-08-06): Settings no validaba config critica al arrancar --
fuera de development, ahora falla explicito en vez de recien en el primer
request real."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_development_does_not_require_critical_config():
    # El proposito explicito del default dummy: poder levantar local sin .env.
    settings = Settings(
        environment="development", nvidia_api_key="", admin_api_key="",
        database_url="postgresql+psycopg://lexchiapas:password@localhost:5432/lexchiapas",
    )
    assert settings.environment == "development"


def test_production_requires_nvidia_api_key():
    with pytest.raises(ValidationError, match="nvidia_api_key"):
        Settings(
            environment="production",
            nvidia_api_key="",
            admin_api_key="real-admin-key",
            database_url="postgresql+psycopg://real:real@real-host:5432/lexchiapas",
        )


def test_production_requires_admin_api_key():
    with pytest.raises(ValidationError, match="admin_api_key"):
        Settings(
            environment="production",
            nvidia_api_key="nvapi-real",
            admin_api_key="",
            database_url="postgresql+psycopg://real:real@real-host:5432/lexchiapas",
        )


def test_production_rejects_the_development_database_url_default():
    with pytest.raises(ValidationError, match="database_url"):
        Settings(
            environment="production",
            nvidia_api_key="nvapi-real",
            admin_api_key="real-admin-key",
            database_url="postgresql+psycopg://lexchiapas:password@localhost:5432/lexchiapas",
        )


def test_production_requires_secret_key(monkeypatch):
    # Fase 9.8 (pentest MEDIA): sin SECRET_KEY, las cookies de sesion admin se
    # firmarian con admin_api_key -> forja offline si esa key se filtra.
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="secret_key"):
        Settings(
            environment="production",
            nvidia_api_key="nvapi-real",
            admin_api_key="real-admin-key",
            database_url="postgresql+psycopg://real:real@real-host:5432/lexchiapas",
            secret_key="",
        )


def test_production_rejects_secret_key_equal_to_admin_api_key():
    with pytest.raises(ValidationError, match="secret_key"):
        Settings(
            environment="production",
            nvidia_api_key="nvapi-real",
            admin_api_key="real-admin-key",
            database_url="postgresql+psycopg://real:real@real-host:5432/lexchiapas",
            secret_key="real-admin-key",  # igual a admin_api_key -> rechazado
        )


def test_production_with_all_critical_config_set_does_not_raise():
    settings = Settings(
        environment="production",
        nvidia_api_key="nvapi-real",
        admin_api_key="real-admin-key",
        database_url="postgresql+psycopg://real:real@real-host:5432/lexchiapas",
        secret_key="una-secret-key-distinta-y-larga",
    )
    assert settings.environment == "production"
