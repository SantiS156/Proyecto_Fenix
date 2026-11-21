
"""Receptor HTTP de webhooks del proyecto Fénix."""

import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from fenix.utils.crypto import verify
from fenix.utils.errors import ValidationError
from fenix.services.events import validate
from fenix.utils.state import load
from fenix.services.sqs import queue_url, publish

load_dotenv()

app = FastAPI(title="Fénix Webhook Receiver")

MAX_BODY_SIZE = 16 * 1024
INVENTORY_PATH = "data/inventory.json"


def reject_duplicate_keys(pairs):
    """Rechaza claves JSON duplicadas."""
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError("El JSON contiene claves duplicadas")

        result[key] = value

    return result


async def read_limited_body(request: Request) -> bytes:
    """Lee el cuerpo HTTP sin aceptar más de 16 KiB."""
    body = bytearray()

    async for chunk in request.stream():
        body.extend(chunk)

        if len(body) > MAX_BODY_SIZE:
            raise HTTPException(
                status_code=413,
                detail="El cuerpo supera el tamaño permitido",
            )

    return bytes(body)


@app.post("/webhook", status_code=202)
async def receive_webhook(request: Request):
    """Autentica, valida y publica un evento en SQS."""

    body = await read_limited_body(request)
 
    secret = os.environ.get("WEBHOOK_SECRET")

    if not isinstance(secret, str) or len(secret) < 16:
        raise HTTPException(
            status_code=500,
            detail="Configuración de autenticación inválida",
        )

    signature_header = request.headers.get("X-Webhook-Signature")

    if not signature_header:
        raise HTTPException(
            status_code=401,
            detail="Falta la firma del webhook",
        )

    try:
        verify(secret, signature_header, body)

    except ValidationError:
        raise HTTPException(
            status_code=401,
            detail="Autenticación del webhook inválida",
        ) from None

    try:
        event = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )

    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="El cuerpo no contiene un JSON válido",
        ) from None

    try:
        inventory = load(INVENTORY_PATH)

    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=503,
            detail="No se pudo consultar el inventario",
        ) from None

    if not isinstance(inventory, dict):
        raise HTTPException(
            status_code=503,
            detail="El inventario no tiene un formato válido",
        )

    resources = inventory.get("resources")

    if not isinstance(resources, dict):
        raise HTTPException(
            status_code=503,
            detail="El inventario de recursos no está disponible",
        )

    try:
        validated_event = validate(event, inventory)

    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from None

    prefix = os.environ.get("QUEUE_PREFIX")

    if not prefix:
        raise HTTPException(
            status_code=503,
            detail="No está configurado el prefijo de las colas",
        )

    try:
        url = await run_in_threadpool(queue_url, prefix)

        message_id = await run_in_threadpool(
            publish,
            url,
            validated_event,
        )

    except (BotoCoreError, ClientError, OSError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="No se pudo publicar el evento en SQS",
        ) from None

    return {
        "status": "accepted",
        "event_id": validated_event["event_id"],
        "message_id": message_id,
    }

