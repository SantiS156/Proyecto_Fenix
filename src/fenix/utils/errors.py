"""Excepciones compartidas. Guía de uso revisada por el integrante 1.

Qué lanzar, y quién lo captura

ValidationError: la ENTRADA es inválida o no está autorizada reintentar no la
    arregla. La lanzan events.validate (esquema, tipos, fecha o recurso fuera del
    inventario), crypto.verify (firma ausente, mal formada o fuera de ventana),
    settings (configuración faltante o destino no permitido) y demo (alias ajeno).
    Es una sola clase con varios significados el receptor HTTP las distingue por
    el try que las rodea, no por el tipo.

RetryableError: falla TRANSITORIA que puede resolverse sola (timeout, 429, 5xx,
    instancia en pending, falla simulada). El mensaje se conserva en SQS y vuelve
    a recibirse después del backoff.

PermanentError: falla que reintentar no arregla (recurso inexistente, conflicto de
    event_id, 400/401/403 del proveedor de avisos). El mensaje no se confirma
    SQS lo mueve a la DLQ por RedrivePolicy. Cambia la explicación del log, no el
    camino que sigue el mensaje.

ProjectError: base común. La CLI la captura para registrar el fallo y salir con
    código 1 el worker la captura para no caerse por un solo mensaje.

Regla común: los mensajes son públicos. No incluyen secretos, tokens, URLs
privadas ni el valor recibido en la entrada.
"""

class ProjectError(Exception):
    """Error controlado del TP: base para informar y cerrar con código 1.

    Args:
        message: descripción pública, sin tokens ni URLs privadas.
    """

class ValidationError(ProjectError):
    """Entrada inválida o recurso fuera del inventario autorizado.

    Args:
        message: regla incumplida, sin copiar secretos de la entrada.
    """

class RetryableError(ProjectError):
    """Fallo transitorio que permite una nueva recepción de SQS.

    Args:
        message: descripción del paso pendiente, sin datos sensibles.
    """

class PermanentError(ProjectError):
    """Fallo no recuperable que se conserva hasta llegar a la DLQ.

    Args:
        message: motivo público del rechazo definitivo del evento.
    """
