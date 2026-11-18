
"""Acciones convergentes de reparación EC2 y S3.
La función handle() queda reservada al Integrante 5.
"""
from botocore.exceptions import BotoCoreError, ClientError

from fenix.config.settings import client
from fenix.utils.state import load, save
from fenix.services.events import validate
from fenix.services.notifications import notify
from fenix.utils.errors import (
    ValidationError,
    RetryableError,
    PermanentError
)


# Códigos de AWS que normalmente indican fallos temporales.
TRANSIENT_CODES = {
    "Throttling",
    "ThrottlingException",
    "RequestLimitExceeded",
    "RequestTimeout",
    "RequestTimeoutException",
    "ServiceUnavailable",
    "InternalError",
    "InternalFailure",
    "SlowDown",
    "PriorRequestNotComplete",
    "OperationAborted"
}


def _aws_failure(error: ClientError, operation: str) -> None:
    """Convierte errores AWS en errores del dominio."""

    response = error.response or {}
    details = response.get("Error", {})
    code = details.get("Code", "Unknown")
    status = response.get("ResponseMetadata", {}).get(
        "HTTPStatusCode", 0
    )

    if code in TRANSIENT_CODES or status == 429 or status >= 500:
        raise RetryableError(
            f"Fallo temporal durante {operation}"
        ) from error

    raise PermanentError(
        f"Fallo permanente durante {operation}: {code}"
    ) from error


def _validate_resource(resource: dict, event_type: str) -> tuple[str, str]:
    """Comprueba que el recurso tenga los campos necesarios."""

    if not isinstance(resource, dict):
        raise PermanentError("Registro de recurso inválido")

    resource_type = resource.get("type")
    resource_id = resource.get("id")

    if not isinstance(resource_id, str) or not resource_id:
        raise PermanentError("Identificador de recurso inválido")

    if event_type == "instance.stopped" and resource_type == "ec2":
        return resource_type, resource_id

    if event_type == "bucket.tags_missing" and resource_type == "s3":
        expected = resource.get("expected_tags")

        if not isinstance(expected, dict) or not expected:
            raise PermanentError("Etiquetas esperadas inválidas")

        if not all(
            isinstance(key, str)
            and key
            and isinstance(value, str)
            for key, value in expected.items()
        ):
            raise PermanentError("Formato de etiquetas inválido")

        return resource_type, resource_id

    raise PermanentError(
        "El tipo de evento no coincide con el recurso autorizado"
    )


def _ec2_state(ec2, instance_id: str) -> str:
    """Consulta el estado actual de una instancia EC2."""

    try:
        response = ec2.describe_instances(
            InstanceIds=[instance_id]
        )

    except ClientError as error:
        _aws_failure(error, "consulta de EC2")

    except BotoCoreError as error:
        raise RetryableError(
            "No se pudo consultar EC2 temporalmente"
        ) from error

    reservations = response.get("Reservations", [])

    for reservation in reservations:
        for instance in reservation.get("Instances", []):
            if instance.get("InstanceId") == instance_id:
                state = instance.get("State", {}).get("Name")

                if isinstance(state, str):
                    return state

    raise PermanentError("La instancia EC2 no existe en el inventario")


def _repair_ec2(instance_id: str) -> str:
    """Inicia una instancia detenida y verifica que quede running."""

    ec2 = client("ec2")

    state = _ec2_state(ec2, instance_id)

    if state == "running":
        return "already_ok"

    if state in ("pending", "stopping"):
        raise RetryableError(
            f"La instancia está cambiando de estado: {state}"
        )

    if state != "stopped":
        raise PermanentError(
            f"No se puede reparar una instancia en estado {state}"
        )

    # Solo se inicia si está detenida.
    try:
        ec2.start_instances(
            InstanceIds=[instance_id]
        )

    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")

        # Otra ejecución podría haber iniciado la instancia.
        if code == "IncorrectInstanceState":
            state = _ec2_state(ec2, instance_id)

            if state == "running":
                return "already_ok"

            if state in ("pending", "stopping"):
                raise RetryableError(
                    "La instancia está cambiando de estado"
                ) from error

            _aws_failure(error, "inicio de EC2")

        else:
            _aws_failure(error, "inicio de EC2")

    except BotoCoreError as error:
        raise RetryableError(
            "No se pudo iniciar EC2 temporalmente"
        ) from error

    # No esperamos durante mucho tiempo: comprobamos una vez más.
    final_state = _ec2_state(ec2, instance_id)

    if final_state == "running":
        return "repaired"

    if final_state in ("pending", "stopping", "stopped"):
        raise RetryableError(
            f"La instancia todavía no está running: {final_state}"
        )

    raise PermanentError(
        f"Estado EC2 inesperado después del inicio: {final_state}"
    )


def _read_s3_tags(s3, bucket_name: str) -> dict:
    """Lee las etiquetas de S3; NoSuchTagSet equivale a etiquetas vacías."""

    try:
        response = s3.get_bucket_tagging(
            Bucket=bucket_name
        )

    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")

        if code == "NoSuchTagSet":
            return {}

        _aws_failure(error, "lectura de etiquetas S3")

    except BotoCoreError as error:
        raise RetryableError(
            "No se pudieron consultar las etiquetas S3"
        ) from error

    tags = {}

    for item in response.get("TagSet", []):
        key = item.get("Key")
        value = item.get("Value")

        if not isinstance(key, str) or not isinstance(value, str):
            raise PermanentError("Etiquetas S3 con formato inválido")

        if key in tags:
            raise PermanentError("El bucket contiene etiquetas duplicadas")

        tags[key] = value

    return tags


def _repair_s3(bucket_name: str, expected_tags: dict) -> str:
    """Restaura etiquetas obligatorias y conserva las etiquetas ajenas."""

    s3 = client("s3")

    current_tags = _read_s3_tags(s3, bucket_name)

    # Comprobar si todas las etiquetas obligatorias ya están correctas.
    already_ok = all(
        current_tags.get(key) == value
        for key, value in expected_tags.items()
    )

    if already_ok:
        return "already_ok"

    # Mantener las etiquetas actuales y agregar o corregir las obligatorias.
    merged_tags = current_tags.copy()
    merged_tags.update(expected_tags)

    tag_set = [
        {"Key": key, "Value": value}
        for key, value in merged_tags.items()
    ]

    try:
        s3.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={"TagSet": tag_set}
        )

    except ClientError as error:
        _aws_failure(error, "escritura de etiquetas S3")

    except BotoCoreError as error:
        raise RetryableError(
            "No se pudieron guardar las etiquetas S3"
        ) from error

    # Leer nuevamente para verificar el resultado real.
    final_tags = _read_s3_tags(s3, bucket_name)

    if final_tags != merged_tags:
        raise RetryableError(
            "Las etiquetas S3 no coinciden con el estado esperado"
        )

    return "repaired"


def repair(resource: dict, event_type: str) -> str:
    """Acerca un recurso autorizado a su estado deseado."""

    if event_type not in (
        "instance.stopped",
        "bucket.tags_missing"
    ):
        raise PermanentError("Tipo de evento no permitido")

    resource_type, resource_id = _validate_resource(
        resource,
        event_type
    )

    if resource_type == "ec2":
        return _repair_ec2(resource_id)

    if resource_type == "s3":
        return _repair_s3(
            resource_id,
            resource["expected_tags"]
        )

    raise PermanentError("Tipo de recurso no permitido")


def handle(event: dict) -> None:
    """Reservado al Integrante 5: orquestación durable del evento."""

    # No implementar aquí: corresponde al TODO I5-B.
    raise NotImplementedError(
        "I5-B: integrar reparación, notificación y ledger durable"
    )

