import json
import os
from pathlib import Path
from botocore.exceptions import ClientError

INVENTORY_PATH = Path(os.getenv("FENIX_INVENTORY_FILE", "inventory.json"))
GROUP_TAG_KEY = os.getenv("FENIX_GROUP_TAG_KEY", "ProyectoFenixGroup")
GROUP_TAG_VALUE = os.getenv("FENIX_GROUP_TAG_VALUE", "grupo-01")


def _load_inventory() -> dict:
    if INVENTORY_PATH.exists():
        return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    return {
        "group": GROUP_TAG_VALUE,
        "queues": {},
        "resources": {},
    }


def _save_inventory(inventory: dict) -> None:
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = INVENTORY_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(INVENTORY_PATH)


def ensure_queues(sqs_client, base_name: str, max_receive_count: int = 3) -> dict:
    """Crea o reutiliza la DLQ y la cola estándar con RedrivePolicy.
    Conserva la QueueUrl devuelta por el SDK y guarda el inventario tras cada paso.
    """
    inventory = _load_inventory()
    queues = inventory.setdefault("queues", {})

    dlq_name = f"{base_name}-dlq"
    main_name = f"{base_name}-queue"
    tags = {GROUP_TAG_KEY: GROUP_TAG_VALUE, "Component": "messaging"}

    # 1. DLQ
    try:
        dlq_url = sqs_client.get_queue_url(QueueName=dlq_name)["QueueUrl"]
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "")
        if code not in ("AWS.SimpleQueueService.NonExistentQueue", "QueueDoesNotExist"):
            raise
        dlq_url = sqs_client.create_queue(QueueName=dlq_name, tags=tags)["QueueUrl"]

    dlq_arn = sqs_client.get_queue_attributes(
        QueueUrl=dlq_url,
        AttributeNames=["QueueArn"],
    )["Attributes"]["QueueArn"]

    queues["dlq"] = {
        "name": dlq_name,
        "url": dlq_url,
        "arn": dlq_arn,
    }
    _save_inventory(inventory)

    # 2. Cola estándar vinculada a la DLQ con RedrivePolicy
    redrive_policy = json.dumps({
        "deadLetterTargetArn": dlq_arn,
        "maxReceiveCount": max_receive_count,
    })

    try:
        main_url = sqs_client.get_queue_url(QueueName=main_name)["QueueUrl"]
        sqs_client.set_queue_attributes(
            QueueUrl=main_url,
            Attributes={"RedrivePolicy": redrive_policy},
        )
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "")
        if code not in ("AWS.SimpleQueueService.NonExistentQueue", "QueueDoesNotExist"):
            raise
        main_url = sqs_client.create_queue(
            QueueName=main_name,
            Attributes={"RedrivePolicy": redrive_policy},
            tags=tags,
        )["QueueUrl"]

    main_arn = sqs_client.get_queue_attributes(
        QueueUrl=main_url,
        AttributeNames=["QueueArn"],
    )["Attributes"]["QueueArn"]

    queues["main"] = {
        "name": main_name,
        "url": main_url,
        "arn": main_arn,
        "maxReceiveCount": max_receive_count,
    }
    _save_inventory(inventory)

    return queues


def retry_later(sqs_client, queue_url: str, message: dict, delay_seconds: int = 30) -> str:
    """Reenvía el mensaje con DelaySeconds (0..900) y elimina la recepción actual."""
    clamped_delay = max(0, min(900, int(delay_seconds)))
    send_kwargs = {
        "QueueUrl": queue_url,
        "MessageBody": message["Body"],
        "DelaySeconds": clamped_delay,
    }
    if message.get("MessageAttributes"):
        send_kwargs["MessageAttributes"] = message["MessageAttributes"]

    sent = sqs_client.send_message(**send_kwargs)

    if "ReceiptHandle" in message:
        sqs_client.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=message["ReceiptHandle"],
        )

    return sent["MessageId"]


def read_dlq(sqs_client, dlq_url: str, max_messages: int = 5, wait_time: int = 2) -> list[dict]:
    """Lee mensajes disponibles en la DLQ."""
    response = sqs_client.receive_message(
        QueueUrl=dlq_url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_time,
        AttributeNames=["All"],
        MessageAttributeNames=["All"],
    )
    return response.get("Messages", [])
