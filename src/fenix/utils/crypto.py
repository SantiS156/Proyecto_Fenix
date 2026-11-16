"""Firma y verificación HMAC de los webhooks."""
import hashlib
import hmac
import re
import time

from fenix.utils.errors import ValidationError


def signature(secret: str, timestamp: int, body: bytes) -> str:
    """Genera una firma HMAC-SHA256 del timestamp y cuerpo original."""

    if not isinstance(secret, str) or len(secret) < 16:
        raise ValidationError(
            "Configurar WEBHOOK_SECRET de 16 caracteres o más"
        )

    if type(timestamp) is not int:
        raise ValidationError("Timestamp inválido")

    if not isinstance(body, bytes):
        raise ValidationError("El cuerpo debe estar expresado en bytes")

    signed = str(timestamp).encode("ascii") + b"." + body

    return hmac.new(
        secret.encode("utf-8"),
        signed,
        hashlib.sha256
    ).hexdigest()


def verify(
    secret: str,
    header: str,
    body: bytes,
    now: int | None = None
) -> None:
    """Verifica formato, antigüedad y autenticidad del webhook."""

    if not isinstance(secret, str) or len(secret) < 16:
        raise ValidationError("Configuración de secreto inválida")

    if not isinstance(header, str):
        raise ValidationError("Cabecera de autenticación inválida")

    if not isinstance(body, bytes):
        raise ValidationError("Cuerpo de autenticación inválido")

    try:
        partes = header.split(",")

        if len(partes) != 2:
            raise ValueError

        campos = {}

        for parte in partes:
            clave, separador, valor = parte.partition("=")

            if not separador or not clave or not valor:
                raise ValueError

            if clave in campos:
                raise ValueError

            campos[clave] = valor

        if set(campos) != {"t", "v1"}:
            raise ValueError

        timestamp_text = campos["t"]
        firma_recibida = campos["v1"]

        if not re.fullmatch(r"[0-9]+", timestamp_text):
            raise ValueError

        if not re.fullmatch(r"[0-9a-fA-F]{64}", firma_recibida):
            raise ValueError

        timestamp = int(timestamp_text)

    except (ValueError, TypeError):
        raise ValidationError(
            "Cabecera de autenticación inválida"
        ) from None

    reloj = int(time.time()) if now is None else now

    if type(reloj) is not int:
        raise ValidationError("Reloj de verificación inválido")

    if abs(reloj - timestamp) > 300:
        raise ValidationError(
            "Timestamp fuera de la ventana permitida"
        )

    firma_calculada = signature(secret, timestamp, body)

    if not hmac.compare_digest(
        firma_recibida.lower(),
        firma_calculada
    ):
        raise ValidationError("Firma HMAC no válida")
