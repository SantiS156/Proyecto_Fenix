
"""Pruebas del integrante 4: Telegram y compresión GZIP."""

import gzip
import logging
from logging.handlers import RotatingFileHandler

import pytest
import requests

from fenix.services import notifications
from fenix.utils.errors import PermanentError, RetryableError
from fenix.utils.logging_json import JSONFormatter, gzip_name, gzip_rotate


class FakeResponse:
    """Simula respuestas del proveedor Telegram."""

    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_telegram_success(monkeypatch):
    """Comprueba el envío exitoso de una notificación."""

    monkeypatch.setenv("NOTIFY_PROVIDER", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-ficticio")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    monkeypatch.setattr(
        notifications.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            payload={"ok": True}
        )
    )

    assert notifications.notify("Prueba Fenix") is None



def test_telegram_missing_credentials(monkeypatch):
    """Comprueba que se rechacen credenciales faltantes."""

    monkeypatch.setenv("NOTIFY_PROVIDER", "telegram")

    # Simular credenciales vacías
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")

    with pytest.raises(PermanentError):
        notifications.notify("Prueba Fenix")



@pytest.mark.parametrize("status", [429, 500, 503])
def test_telegram_retryable_error(monkeypatch, status):
    """Comprueba que los errores temporales permitan reintentar."""

    monkeypatch.setenv("NOTIFY_PROVIDER", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-ficticio")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    monkeypatch.setattr(
        notifications.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(status=status)
    )

    with pytest.raises(RetryableError):
        notifications.notify("Prueba Fenix")


@pytest.mark.parametrize("status", [400, 401, 403])
def test_telegram_permanent_error(monkeypatch, status):
    """Comprueba que los errores definitivos no se reintenten."""

    monkeypatch.setenv("NOTIFY_PROVIDER", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-ficticio")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    monkeypatch.setattr(
        notifications.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(status=status)
    )

    with pytest.raises(PermanentError):
        notifications.notify("Prueba Fenix")


def test_telegram_connection_error(monkeypatch):
    """Comprueba el tratamiento de fallos de conexión."""

    monkeypatch.setenv("NOTIFY_PROVIDER", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-ficticio")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    def fail(*args, **kwargs):
        raise requests.Timeout("Tiempo agotado")

    monkeypatch.setattr(notifications.requests, "post", fail)

    with pytest.raises(RetryableError):
        notifications.notify("Prueba Fenix")


def test_gzip_rotation(tmp_path):
    """Comprueba la rotación y lectura de históricos GZIP."""

    archivo = tmp_path / "prueba.jsonl"

    handler = RotatingFileHandler(
        archivo,
        maxBytes=300,
        backupCount=3,
        encoding="utf-8"
    )

    handler.setFormatter(JSONFormatter())
    handler.namer = gzip_name
    handler.rotator = gzip_rotate

    logger = logging.getLogger("test_i4_gzip")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False

    try:
        for i in range(20):
            logger.info(
                f"Registro {i}",
                extra={
                    "event_id": f"evento-{i}",
                    "action": "test",
                    "status": "success"
                }
            )
    finally:
        logger.removeHandler(handler)
        handler.close()

    archivos_gzip = list(tmp_path.glob("*.gz"))

    assert archivos_gzip, "No se generaron archivos GZIP"

    for archivo_gzip in archivos_gzip:
        with gzip.open(
            archivo_gzip, "rt", encoding="utf-8"
        ) as contenido:
            for linea in contenido:
                assert "event_id" in linea
