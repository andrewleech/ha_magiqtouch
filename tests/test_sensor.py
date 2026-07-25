"""Tests for MagIQtouch temperature sensor availability."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.const import UnitOfTemperature

from custom_components.magiqtouch.sensor import TemperatureSensor
from custom_components.magiqtouch.structures import RemoteStatus


def make_sensor(value, *, unit=UnitOfTemperature.CELSIUS):
    controller = SimpleNamespace(
        native_unit_of_measurement=unit,
        device_id="synthetic-device",
        device_name="Synthetic MagIQtouch",
        current_state=RemoteStatus(device="synthetic-device"),
        get_zone_name=Mock(return_value="Common"),
    )
    entity = TemperatureSensor(
        "Temperature",
        controller,
        SimpleNamespace(last_update_success=True),
        data_callback=Mock(return_value=value),
    )
    entity.async_write_ha_state = Mock()
    return entity


@pytest.mark.parametrize("value", [None, float("nan"), 255.0])
def test_invalid_temperature_marks_sensor_unavailable(value) -> None:
    entity = make_sensor(value)

    entity._handle_coordinator_update()

    assert entity.native_value is None
    assert entity.available is False
    entity.async_write_ha_state.assert_called_once_with()


def test_valid_temperature_updates_sensor() -> None:
    entity = make_sensor(22.5)

    entity._handle_coordinator_update()

    assert entity.native_value == 22.5
    assert entity.available is True


def test_valid_fahrenheit_temperature_above_100_is_available() -> None:
    entity = make_sensor(105.0, unit=UnitOfTemperature.FAHRENHEIT)

    entity._handle_coordinator_update()

    assert entity.native_value == 105.0
    assert entity.available is True


def test_missing_active_device_marks_sensor_unavailable() -> None:
    entity = make_sensor(22.0)
    entity.data_callback.side_effect = AttributeError("synthetic missing device")

    entity._handle_coordinator_update()

    assert entity.native_value is None
    assert entity.available is False
