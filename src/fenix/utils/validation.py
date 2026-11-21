"""Validaciones del integrante 1: identifier, ttl_seconds y utc_text."""
import re  # Comprueba el formato de los identificadores.
from datetime import datetime, timedelta, timezone  # Trabaja con fechas conscientes de UTC.
from fenix.utils.errors import ValidationError  # Error público del dominio.


def identifier(value: str) -> str:
    """Valida un identificador corto y devuelve su texto sin modificar.

    Args:
        value: Texto entre 3 y 32 caracteres: letras minúsculas, dígitos o guion.
    Returns:
        El identificador original válido.
    Raises:
        ValidationError: Si el tipo o el patrón no cumplen el contrato.
    Examples:
        identifier("grupo-01") devuelve "grupo-01".
    """
    # Primero el tipo si no es texto, re.fullmatch lanzaría TypeError.
    if not isinstance(value, str):
        raise ValidationError("identifier debe ser texto")
    # fullmatch exige que coincida TODO el texto.
    # No se convierte a minúsculas: eso cambiaría la identidad recibida.
    if re.fullmatch(r"[a-z0-9-]{3,32}", value) is None:
        # El mensaje no copia el valor recibido, por si trae datos sensibles.
        raise ValidationError(
            "identifier debe tener 3 a 32 caracteres: minúsculas, dígitos o guion"
        )
    return value


def ttl_seconds(value: str) -> int:
    """Valida el TTL didáctico empleado en la opción de entornos efímeros.

    Args:
        value: Texto con un entero entre 60 y 600 segundos inclusive.
    Returns:
        El número entero de segundos.
    Raises:
        ValidationError: Si no es entero o está fuera de los límites.
    Notes:
        La CLI traduce ValidationError a parser.error para salir con código 2.
    """
    # Solo texto int truncaría a 60 sin avisar, y int(True) daría 1.
    if not isinstance(value, str):
        raise ValidationError("ttl debe ser texto con un entero")
    try:
        ttl = int(value)
    except ValueError as error:
        # "from error" conserva la causa original para diagnosticar.
        raise ValidationError("ttl debe ser un entero") from error
    if not 60 <= ttl <= 600:
        raise ValidationError("ttl debe estar entre 60 y 600 segundos")
    return ttl


def utc_text(value: str) -> datetime:
    """Interpreta una fecha UTC explícita sin aceptar fechas ingenuas.

    Args:
        value: ISO 8601 terminado en Z o con offset +00:00.
    Returns:
        Fecha con zona UTC por ejemplo 2026-10-22T18:00:00+00:00.
    Raises:
        ValidationError: Si falta zona, hay offset no nulo o formato inválido.
    """
    # Solo texto cualquier otro tipo no puede ser una fecha ISO 8601.
    if not isinstance(value, str):
        raise ValidationError("la fecha debe ser texto ISO 8601")
    # Se reemplaza solo la Z final por +00:00.
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValidationError("fecha con formato ISO 8601 inválido") from error
    # Sin zona o con un offset distinto de cero no es UTC.
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValidationError("la fecha debe ser UTC explícita (Z o +00:00)")
    return parsed.astimezone(timezone.utc)
