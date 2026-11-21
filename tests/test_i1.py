"""Pruebas del integrante 1 identifier, ttl_seconds, utc_text y events.validate."""
import copy
import json
from pathlib import Path
import pytest

from fenix.services.events import validate
from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, ttl_seconds, utc_text

INVENTARIO = {
    "group": "grupo01",
    "resources": {
        "node-01": {"type": "ec2", "id": "i-0001"},
        "bucket-01": {"type": "s3", "id": "bucket-prueba"},
    },
}
EVENTO_NODO = {
    "schema_version": 1,
    "event_id": "evt-node-001",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-10-22T18:00:00Z",
    "simulate_failures": 0,
}


@pytest.mark.parametrize("valor", ["grupo-01", "abc", "a" * 32])
def test_identifier_acepta(valor):
    assert identifier(valor) == valor


@pytest.mark.parametrize("valor", ["../ajeno", "ab", "Grupo-01", "abc\n", "a" * 33, 123, None])
def test_identifier_rechaza(valor):
    with pytest.raises(ValidationError):
        identifier(valor)


@pytest.mark.parametrize("valor, esperado", [("60", 60), ("120", 120), ("600", 600)])
def test_ttl_acepta(valor, esperado):
    assert ttl_seconds(valor) == esperado


@pytest.mark.parametrize("valor", ["59", "601", "60.5", "-5", "abc", 60])
def test_ttl_rechaza(valor):
    with pytest.raises(ValidationError):
        ttl_seconds(valor)


@pytest.mark.parametrize("valor", ["2026-10-22T18:00:00Z", "2026-10-22T18:00:00+00:00"])
def test_utc_acepta(valor):
    assert utc_text(valor).utcoffset().total_seconds() == 0


@pytest.mark.parametrize(
    "valor",
    ["2026-10-22T18:00:00", "2026-10-22T13:00:00-05:00", "2026-10-22", "hoy", 123, None],
)
def test_utc_rechaza(valor):
    with pytest.raises(ValidationError):
        utc_text(valor)


def test_validate_evento_correcto_devuelve_copia():
    inventario_antes = copy.deepcopy(INVENTARIO)
    resultado = validate(EVENTO_NODO, INVENTARIO)
    assert resultado == EVENTO_NODO
    assert resultado is not EVENTO_NODO  # es una copia
    assert INVENTARIO == inventario_antes  # no modifica el inventario


@pytest.mark.parametrize(
    "evento",
    [
        [EVENTO_NODO],  # una lista JSON no es un evento
        {**EVENTO_NODO, "extra": 1},  # clave extra
        {k: v for k, v in EVENTO_NODO.items() if k != "occurred_at"},  # clave ausente
        {**EVENTO_NODO, "schema_version": True},  # bool como entero
        {**EVENTO_NODO, "schema_version": 1.0},  # float como entero
        {**EVENTO_NODO, "simulate_failures": True},
        {**EVENTO_NODO, "simulate_failures": 6},
        {**EVENTO_NODO, "event_type": "x.y"},  # tipo desconocido
        {**EVENTO_NODO, "event_type": ["a"]},  # tipo no hashable
        {**EVENTO_NODO, "resource_id": "otro-99"},  # recurso ajeno
        {**EVENTO_NODO, "resource_id": "../ajeno"},
        {**EVENTO_NODO, "event_type": "bucket.tags_missing"},  # tipo no corresponde al recurso
        {**EVENTO_NODO, "occurred_at": "2026-10-22T18:00:00"},  # fecha sin zona
    ],
)
def test_validate_rechaza(evento):
    with pytest.raises(ValidationError):
        validate(evento, INVENTARIO)


EJEMPLOS = Path(__file__).resolve().parent.parent / "examples"


def cargar(nombre):
    return json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))


@pytest.mark.parametrize("nombre", ["node-event.json", "bucket-event.json"])
def test_ejemplos_validos_se_aceptan(nombre):
    evento = cargar(nombre)
    assert validate(evento, INVENTARIO) == evento


@pytest.mark.parametrize(
    "nombre",
    ["invalid-list.json", "invalid-extra-key.json", "invalid-foreign-resource.json"],
)
def test_ejemplos_invalidos_se_rechazan(nombre):
    with pytest.raises(ValidationError):
        validate(cargar(nombre), INVENTARIO)