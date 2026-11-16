
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

    # 1. Leer el cuerpo original en bytes.
    raw = await request.body()

    # 2. Comprobar el tamaño máximo permitido: 16 KiB.
    if len(raw) > 16384:
        raise HTTPException(
            status_code=413,
            detail="Cuerpo demasiado grande"
        )

    # 3. Obtener la configuración del receptor.
    secret = os.environ.get("WEBHOOK_SECRET")
    prefix = os.environ.get("QUEUE_PREFIX")

    if not secret or len(secret) < 16 or not prefix:
        raise HTTPException(
            status_code=503,
            detail="Configuración del receptor incompleta"
        )

    # 4. Verificar la firma antes de interpretar el JSON.
    header = request.headers.get("X-Webhook-Signature")

    try:
        verify(secret, header, raw)
    except ValidationError:
        raise HTTPException(
            status_code=401,
            detail="Autenticación inválida"
        ) from None

    # 5. Decodificar el JSON solamente después de autenticar.
    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=400,
            detail="El cuerpo no contiene JSON válido"
        ) from None

    # 6. Cargar el inventario sin bloquear el event loop.
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

    # 7. Validar el contrato y el alias del recurso.
    try:
        validated_event = validate(event, inventory)
    except ValidationError:
        raise HTTPException(
            status_code=422,
            detail="Evento o recurso no autorizado"
        ) from None

    # 8. Obtener la URL de la cola y publicar el evento.
    try:
        url = await run_in_threadpool(queue_url, prefix)

        message_id = await run_in_threadpool(
            publish,
            url,
            validated_event
        )

        # No confirmar si SQS no devuelve un identificador válido.
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

    # 9. Confirmar solamente después de la publicación exitosa.
    return {
        "status": "accepted",
        "event_id": validated_event["event_id"],
        "message_id": message_id
    }

