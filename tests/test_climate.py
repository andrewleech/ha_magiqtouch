"""Tests for capability-driven MagIQtouch climate behaviour."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature

from custom_components.magiqtouch.climate import (
    FAN_SPEED_BY_TEMP,
    FAN_SPEED_TO_PREV,
    MagIQtouch,
    PRESET_COOL_FAN_SPEED,
    PRESET_COOL_TEMP,
)
from custom_components.magiqtouch.const import (
    MODE_COOLER,
    MODE_COOLER_FAN,
    MODE_HEATER,
    MODE_HEATER_FAN,
)
from custom_components.magiqtouch.structures import Fan, Installed, RemoteStatus


def make_entity(
    *,
    coolers=None,
    heaters=None,
    running_mode=MODE_COOLER,
    system_on=True,
    cooler_fan=True,
    heater_fan=True,
):
    coolers = list(coolers or [])
    heaters = list(heaters or [])
    state = RemoteStatus(
        device="synthetic-device",
        runningMode=running_mode,
        systemOn=system_on,
        cooler=coolers,
        heater=heaters,
        fan=Fan(
            cooler_available=cooler_fan and bool(coolers),
            heater_available=heater_fan and bool(heaters),
        ),
        installed=Installed(evap=bool(coolers), heater=bool(heaters)),
    )
    controller = SimpleNamespace(
        device_id="synthetic-device",
        device_name="Synthetic MagIQtouch",
        current_state=state,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        logged_in=True,
        available_coolers=Mock(side_effect=lambda zone: coolers),
        available_heaters=Mock(side_effect=lambda zone: heaters),
        get_zone_name=Mock(return_value="Common"),
        set_cooling_by_temperature=AsyncMock(),
        set_cooling_by_speed=AsyncMock(),
        set_heating_by_temperature=AsyncMock(),
        set_heating_by_speed=AsyncMock(),
        set_current_speed=AsyncMock(),
    )

    def active_device(zone):
        if state.runningMode in (MODE_COOLER, MODE_COOLER_FAN) and coolers:
            return coolers[0]
        if state.runningMode in (MODE_HEATER, MODE_HEATER_FAN) and heaters:
            return heaters[0]
        return (coolers or heaters or [None])[0]

    controller.active_device = Mock(side_effect=active_device)
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    return MagIQtouch("synthetic-entry", controller, coordinator), controller


def test_cooling_only_entity_does_not_expose_heat(make_unit) -> None:
    entity, _ = make_entity(coolers=[make_unit()])

    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.FAN_ONLY, HVACMode.COOL]


def test_heating_only_entity_does_not_expose_cool(make_unit) -> None:
    entity, _ = make_entity(heaters=[make_unit()], running_mode=MODE_HEATER)

    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.FAN_ONLY, HVACMode.HEAT]


def test_entity_does_not_expose_unsupported_fan_only(make_unit) -> None:
    entity, _ = make_entity(coolers=[make_unit()], cooler_fan=False)

    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.COOL]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("running_mode", "equipment", "method_name"),
    [
        (MODE_COOLER, "coolers", "set_cooling_by_temperature"),
        (MODE_HEATER, "heaters", "set_heating_by_temperature"),
    ],
)
async def test_temperature_fan_mode_routes_to_active_equipment(
    make_unit, running_mode, equipment, method_name
) -> None:
    entity, controller = make_entity(
        coolers=[make_unit()] if equipment == "coolers" else [],
        heaters=[make_unit()] if equipment == "heaters" else [],
        running_mode=running_mode,
    )

    await entity.async_set_fan_mode(FAN_SPEED_BY_TEMP)

    getattr(controller, method_name).assert_awaited_once_with(entity.zone)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("running_mode", "equipment", "method_name"),
    [
        (MODE_COOLER, "coolers", "set_cooling_by_speed"),
        (MODE_HEATER, "heaters", "set_heating_by_speed"),
    ],
)
async def test_previous_fan_mode_routes_to_active_equipment(
    make_unit, running_mode, equipment, method_name
) -> None:
    entity, controller = make_entity(
        coolers=[make_unit()] if equipment == "coolers" else [],
        heaters=[make_unit()] if equipment == "heaters" else [],
        running_mode=running_mode,
    )

    await entity.async_set_fan_mode(FAN_SPEED_TO_PREV)

    getattr(controller, method_name).assert_awaited_once_with(entity.zone)


@pytest.mark.asyncio
async def test_off_system_uses_only_installed_equipment_as_safe_fallback(make_unit) -> None:
    entity, controller = make_entity(
        coolers=[make_unit()],
        running_mode="",
        system_on=False,
    )

    await entity.async_set_fan_mode(FAN_SPEED_BY_TEMP)

    controller.set_cooling_by_temperature.assert_awaited_once_with(entity.zone)


@pytest.mark.asyncio
async def test_off_combined_system_does_not_guess_equipment(make_unit, caplog) -> None:
    entity, controller = make_entity(
        coolers=[make_unit()],
        heaters=[make_unit()],
        running_mode="",
        system_on=False,
    )

    with caplog.at_level(logging.WARNING, logger="magiqtouch"):
        await entity.async_set_fan_mode(FAN_SPEED_BY_TEMP)

    controller.set_cooling_by_temperature.assert_not_called()
    controller.set_heating_by_temperature.assert_not_called()
    assert "cannot determine active equipment" in caplog.text.lower()


@pytest.mark.asyncio
async def test_numeric_fan_mode_keeps_existing_speed_command(make_unit) -> None:
    entity, controller = make_entity(coolers=[make_unit()])

    await entity.async_set_fan_mode("5")

    controller.set_current_speed.assert_awaited_once_with("5")


def test_current_temperature_returns_valid_reading(make_unit) -> None:
    entity, _ = make_entity(coolers=[make_unit(internal_temp=22.0)])

    assert entity.current_temperature == 22.0


def test_current_temperature_averages_only_valid_readings(make_unit) -> None:
    entity, _ = make_entity(
        coolers=[
            make_unit(internal_temp=20.0),
            make_unit(name="Bedroom", zone_type="ZONE_1", internal_temp=24.0),
            make_unit(name="Study", zone_type="ZONE_2", internal_temp=255.0),
        ]
    )

    assert entity.current_temperature == 22.0


def test_no_units_return_unavailable_temperature_properties() -> None:
    entity, _ = make_entity(coolers=[], heaters=[], running_mode="", system_on=False)

    assert entity.current_temperature is None
    assert entity.target_temperature is None
    assert entity.min_temp is None
    assert entity.max_temp is None
    assert entity.fan_mode is None


def test_no_valid_sensor_does_not_fabricate_target_as_current(make_unit) -> None:
    entity, _ = make_entity(coolers=[make_unit(internal_temp=255.0, set_temp=24.0)])

    assert entity.current_temperature is None
    assert entity.target_temperature is None
    assert entity.min_temp is None
    assert entity.max_temp is None


def test_fan_control_remains_available_without_temperature_sensor(make_unit) -> None:
    entity, _ = make_entity(coolers=[make_unit(internal_temp=255.0)])

    assert entity.supported_features & ClimateEntityFeature.FAN_MODE
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert FAN_SPEED_BY_TEMP not in entity.fan_modes
    assert FAN_SPEED_TO_PREV not in entity.fan_modes
    assert entity.fan_modes == [str(speed) for speed in range(1, 11)]
    assert PRESET_COOL_TEMP not in entity.preset_modes
    assert PRESET_COOL_FAN_SPEED in entity.preset_modes


@pytest.mark.asyncio
async def test_temperature_mode_is_rejected_without_temperature_sensor(
    make_unit, caplog
) -> None:
    entity, controller = make_entity(coolers=[make_unit(internal_temp=255.0)])

    with caplog.at_level(logging.WARNING, logger="magiqtouch"):
        await entity.async_set_fan_mode(FAN_SPEED_BY_TEMP)

    controller.set_cooling_by_temperature.assert_not_called()
    assert "unknown fan speed" in caplog.text.lower()
