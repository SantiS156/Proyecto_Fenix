"""Guía ejecutable del integrante 6; sustituir cada pendiente por aserciones reales."""
import json
import fenix.services.remediation as remediation
import fenix.utils.state as state
import pytest  # Mantiene visibles los casos sin implementar.
import fenix.services.worker as worker
from fenix.utils.errors import RetryableError

def test_duplicate_is_idempotent(tmp_path, monkeypatch):
    """Comprueba que repetir un evento no repite reparación ni notificación."""

    # Guardado real, pero aislado dentro de tmp_path.
    data_dir = tmp_path / "data"

    def load_test(path):
        return state.load(data_dir / path.split("/")[-1])

    def save_test(path, data):
        state.save(data_dir / path.split("/")[-1], data)

    # Crear un inventario válido para el evento.
    inventory = {
        "demo-ec2": {
            "type": "ec2",
            "id": "i-1234567890abcdef0"
        }
    }
    save_test("data/inventory.json", inventory)

    # Reemplazar las rutas de almacenamiento del handler.
    monkeypatch.setattr(remediation, "load", load_test)
    monkeypatch.setattr(remediation, "save", save_test)

    # Contar cuántas veces se ejecutan reparación y notificación.
    repair_calls = []
    notification_calls = []

    def fake_repair(resource, event_type):
        repair_calls.append((resource, event_type))
        return "repaired"

    def fake_notify(message):
        notification_calls.append(message)

    monkeypatch.setattr(remediation, "repair", fake_repair)
    monkeypatch.setattr(remediation, "notify", fake_notify)

    event = {
        "schema_version": 1,
        "event_id": "evt-duplicate-001",
        "event_type": "instance.stopped",
        "resource_id": "demo-ec2",
        "occurred_at": "2026-01-01T00:00:00Z",
        "simulate_failures": 0
    }

    # Primera ejecución: debe reparar y notificar.
    remediation.handle(event)

    # Comprobar que el estado quedó guardado en disco.
    saved_ledger = load_test("data/events.json")
    assert saved_ledger["evt-duplicate-001"]["status"] == "completed"

    # Segunda ejecución: debe reconocer el evento ya completado.
    remediation.handle(event)

    # La reparación y la notificación deben haberse ejecutado una sola vez.
    assert len(repair_calls) == 1
    assert len(notification_calls) == 1

    # Confirmar que el estado final sigue completado.
    final_ledger = load_test("data/events.json")
    assert final_ledger["evt-duplicate-001"]["repair_done"] is True
    assert final_ledger["evt-duplicate-001"]["notified"] is True
    assert final_ledger["evt-duplicate-001"]["status"] == "completed"



def test_ack_is_after_success(monkeypatch):
    """Verifica que un handler fallido no confirme el mensaje."""

    message = {
        "MessageId": "msg-test-001",
        "ReceiptHandle": "receipt-test-001",
        "Body": json.dumps({
            "event_id": "evt-test-001"
        })
    }

    calls = []

    # Logger falso: evita depender del sistema de logs.
    class FakeLogger:
        def error(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            pass

    logger = FakeLogger()

    # Simular el transporte SQS.
    monkeypatch.setattr(worker, "receive", lambda url: [message])
    monkeypatch.setattr(
        worker, "retry_later",
        lambda url, msg: calls.append("retry")
    )
    monkeypatch.setattr(
        worker, "acknowledge",
        lambda url, receipt: calls.append("ack")
    )

    # Evitar acceso al ledger real en la ejecución exitosa.
    monkeypatch.setattr(
        worker, "load",
        lambda path: {"evt-test-001": {}}
    )
    monkeypatch.setattr(worker, "save", lambda path, data: None)

    # Caso 1: el handler falla. Debe reintentar y nunca confirmar.
    def failing_handler(event):
        calls.append("handler")
        raise RetryableError("Fallo temporal de prueba")

    worker.run("fake-queue-url", failing_handler, logger, once=True)

    assert calls == ["handler", "retry"]
    assert "ack" not in calls

    # Caso 2: el handler termina correctamente.
    calls.clear()

    def successful_handler(event):
        calls.append("handler")

    worker.run("fake-queue-url", successful_handler, logger, once=True)

    assert calls == ["handler", "ack"]


@pytest.mark.integracion
def test_redrive_with_localstack():
    """Comprueba DLQ efectiva usando el broker, no una lista simulada en Python.

    Returns:
        None si un mensaje venenoso termina en la DLQ y el worker sigue vivo.
    Raises:
        NotImplementedError: Hasta implementar el ensayo con espera total acotada.
    Side Effects:
        Crea colas de prueba exclusivas y las limpia después de guardar evidencia.
    Notes:
        Usar un prefijo de test nuevo y no purgar colas del laboratorio del grupo.
    """
    # TODO I6-D: publicar JSON corrupto en una cola con RedrivePolicy real.
    # Consumir con el worker y consultar DLQ con deadline total de 120 segundos.
    # Comparar el Body original; un contador aproximado por sí solo no demuestra redrive.
    # Si se agota el deadline, fallar con diagnóstico; no pasar el test por timeout.
    raise NotImplementedError("I6-D: verificar redrive real en LocalStack")
