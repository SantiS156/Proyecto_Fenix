
"""Receptor FastAPI: autenticación, validación y aceptación durable por SQS."""
import json
import os

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from botocore.exceptions import BotoCoreError, ClientError

from fenix.utils.crypto import verify
from fenix.utils.errors import ValidationError
from fenix.utils.state import load
from fenix.services.events import validate
from fenix.services.sqs import queue_url, publish


app = FastAPI(title="Fénix receptor de alertas")


@app.post("/webhook", status_code=202)
async def webhook(request: Request) -> dict:
    """Autentica, valida y publica un evento en SQS."""

    raw = await request.body()

    if len(raw) > 16384:
        raise HTTPException(
            status_code=413,
            detail="Cuerpo demasiado grande"
        )

    secret = os.environ.get("WEBHOOK_SECRET")
    prefix = os.environ.get("QUEUE_PREFIX")

    if not secret or len(secret) < 16 or not prefix:
        raise HTTPException(
            status_code=503,
            detail="Configuración del receptor incompleta"
        )

    header = request.headers.get("X-Webhook-Signature")

    try:
        verify(secret, header, raw)
    except ValidationError:
        raise HTTPException(
            status_code=401,
            detail="Autenticación inválida"
        ) from None

    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=400,
            detail="El cuerpo no contiene JSON válido"
        ) from None

    try:
        inventory = await run_in_threadpool(
            load,
            "data/inventory.json"
        )
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=503,
            detail="No se pudo consultar el inventario"
        ) from None

    try:
        validated_event = validate(event, inventory)
    except ValidationError:
        raise HTTPException(
            status_code=422,
            detail="Evento o recurso no autorizado"
        ) from None

    try:
        url = await run_in_threadpool(queue_url, prefix)

        message_id = await run_in_threadpool(
            publish,
            url,
            validated_event
        )

        if not isinstance(message_id, str) or not message_id:
            raise HTTPException(
                status_code=503,
                detail="SQS no confirmó la publicación"
            )

    except HTTPException:
        raise
    except (ClientError, BotoCoreError, ValidationError):
        raise HTTPException(
            status_code=503,
            detail="No se pudo publicar el evento en SQS"
        ) from None

    return {
        "status": "accepted",
        "event_id": validated_event["event_id"],
        "message_id": message_id
    }

