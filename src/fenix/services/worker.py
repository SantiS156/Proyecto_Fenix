
"""Worker central de integración: procesa mensajes de la cola."""

import json
import time

from botocore.exceptions import BotoCoreError, ClientError

from fenix.services.sqs import receive, acknowledge, retry_later
from fenix.utils.errors import ProjectError
from fenix.utils.state import load, save


def run(url: str, handler, logger, once: bool = False) -> None:
    """Consume mensajes y confirma únicamente resultados durables."""

    try:
        while True:
            try:
                messages = receive(url)

            except (BotoCoreError, ClientError) as error:
                logger.error(
                    "Error al recibir mensajes SQS",
                    extra={"error_type": type(error).__name__},
                )
                time.sleep(2)

            else:
                for message in messages:
                    message_id = message.get("MessageId", "unknown")

                    try:
                        event = json.loads(message["Body"])

                        if not isinstance(event, dict):
                            raise ValueError(
                                "El evento debe ser un diccionario"
                            )

                        receipt_handle = message["ReceiptHandle"]
                        handler(event, message_id=message_id)

                    except NotImplementedError:
                        raise

                    except (
                        json.JSONDecodeError,
                        KeyError,
                        TypeError,
                        ValueError,
                        ProjectError,
                        BotoCoreError,
                        ClientError,
                    ) as error:
                        logger.error(
                            "Error al procesar el mensaje",
                            extra={
                                "message_id": message_id,
                                "error_type": type(error).__name__,
                            },
                        )

                        try:
                            retry_later(url, message)
                        except (BotoCoreError, ClientError) as retry_error:
                            logger.error(
                                "Error al reprogramar el mensaje",
                                extra={
                                    "message_id": message_id,
                                    "error_type": type(retry_error).__name__,
                                },
                            )
                            time.sleep(2)

                    else:
                        try:
                            acknowledge(url, receipt_handle)

                        except (BotoCoreError, ClientError) as ack_error:
                            logger.error(
                                "Error al confirmar el mensaje",
                                extra={
                                    "message_id": message_id,
                                    "error_type": type(ack_error).__name__,
                                },
                            )
                            time.sleep(2)

                        else:
                            try:
                                event_id = event["event_id"]
                                ledger = load("data/events.json")

                                if not isinstance(ledger, dict):
                                    raise ValueError(
                                        "El registro de eventos no es válido"
                                    )

                                record = ledger.get(event_id)

                                if not isinstance(record, dict):
                                    raise ValueError(
                                        "No existe un registro válido "
                                        "para el evento confirmado"
                                    )

                                record["status"] = "acknowledged"
                                save("data/events.json", ledger)

                            except (KeyError, OSError, ValueError, TypeError):
                                logger.error(
                                    "No se pudo registrar el ACK en el ledger",
                                    extra={"message_id": message_id},
                                )

            if once:
                break

    except KeyboardInterrupt:
        logger.info("Worker detenido por el usuario")
