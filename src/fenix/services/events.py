"""Contrato de eventos de autorreparación; integrante 1."""
from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, utc_text

# Campos exactos del contrato ni más ni menos.
EVENT_FIELDS = {
    "schema_version", "event_id", "event_type",
    "resource_id", "occurred_at", "simulate_failures",
}
# Cada tipo de evento solo puede aplicarse a un tipo de recurso del inventario.
EVENT_RESOURCE_TYPE = {"instance.stopped": "ec2", "bucket.tags_missing": "s3"}


def validate(event: dict, inventory: dict) -> dict:
    """Valida esquema cerrado y resuelve exclusivamente aliases autorizados.

    Args:
        event: JSON objeto con schema_version, event_id, event_type, resource_id,
            occurred_at y simulate_failures.
        inventory: Mapa alias -> recurso, preparado por setup-demo y revisado por el grupo.
    Returns:
        Copia validada del evento; no modifica inventory.
    Raises:
        ValidationError: Tipo, campo, timestamp o recurso no permitido.
        NotImplementedError: Mientras no se complete TODO I1-D.
    Notes:
        event_type solo permite instance.stopped y bucket.tags_missing.
        simulate_failures solo es de laboratorio: entero de 0 a 5, excluyendo bool.
    """
    # 1 El evento debe ser un objeto JSON una lista JSON no es un evento.
    if not isinstance(event, dict):
        raise ValidationError("el evento debe ser un objeto JSON")
    # 2 Esquema cerrado exactamente los campos del contrato, sin faltantes ni extra.
    if set(event) != EVENT_FIELDS:
        raise ValidationError("el evento no tiene exactamente los campos del contrato")
    # 3 type is int rechaza bool y floats.
    if type(event["schema_version"]) is not int or event["schema_version"] != 1:
        raise ValidationError("schema_version debe ser el entero 1")
    failures = event["simulate_failures"]
    if type(failures) is not int or not 0 <= failures <= 5:
        raise ValidationError("simulate_failures debe ser un entero de 0 a 5")
    # 4 Formato de identificadores y fecha UTC.
    identifier(event["event_id"])
    resource_id = identifier(event["resource_id"])
    utc_text(event["occurred_at"])
    # 5 event_type conocido.
    event_type = event["event_type"]
    if not isinstance(event_type, str) or event_type not in EVENT_RESOURCE_TYPE:
        raise ValidationError("event_type no está permitido")
    # 6 Solo aliases del inventario nunca ARN ni InstanceId elegidos por el remitente.
    resource = inventory.get(resource_id)
    if not isinstance(resource, dict):
        raise ValidationError("resource_id no pertenece al inventario autorizado")
    # 7 El tipo de evento debe corresponder al tipo del recurso.
    if resource.get("type") != EVENT_RESOURCE_TYPE[event_type]:
        raise ValidationError("event_type no corresponde al tipo del recurso")
    # 8 Se devuelve una copia el evento recibido y el inventario no se modifican.
    return dict(event)
