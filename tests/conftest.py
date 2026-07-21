"""Shared synthetic fixtures for the MagIQtouch test suite."""

from collections.abc import Callable

import pytest

from custom_components.magiqtouch.structures import Installed, RemoteStatus, UnitDetails


@pytest.fixture
def make_unit() -> Callable[..., UnitDetails]:
    """Build a synthetic installed unit without using captured cloud data."""

    def _make_unit(
        *,
        name: str = "Common",
        zone_type: str = "COMMON",
        internal_temp: float = 22.0,
        set_temp: float = 24.0,
        control_mode: str = "TEMP",
        fan_speed: int = 5,
    ) -> UnitDetails:
        return UnitDetails(
            name=name,
            zoneType=zone_type,
            internal_temp=internal_temp,
            set_temp=set_temp,
            min_temp=16.0,
            max_temp=32.0,
            control_mode=control_mode,
            fan_speed=fan_speed,
            min_fan_speed=1,
            max_fan_speed=10,
        )

    return _make_unit


@pytest.fixture
def make_remote_status() -> Callable[..., RemoteStatus]:
    """Build a synthetic controller state for a chosen equipment set."""

    def _make_remote_status(
        *,
        cooler: list[UnitDetails] | None = None,
        heater: list[UnitDetails] | None = None,
        running_mode: str = "COOL",
        system_on: bool = True,
    ) -> RemoteStatus:
        coolers = list(cooler or [])
        heaters = list(heater or [])
        return RemoteStatus(
            device="synthetic-device",
            timestamp=1,
            online=True,
            systemOn=system_on,
            runningMode=running_mode,
            cooler=coolers,
            heater=heaters,
            installed=Installed(evap=bool(coolers), heater=bool(heaters)),
        )

    return _make_remote_status
