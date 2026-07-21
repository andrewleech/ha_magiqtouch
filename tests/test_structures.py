"""Tests for cloud state parsing and in-place reconciliation."""

from dataclasses import dataclass

import pytest

from custom_components.magiqtouch.structures import (
    Installed,
    RemoteStatus,
    UnitDetails,
    dataclass_from_dict,
)


def test_remote_status_ignores_unknown_top_level_field() -> None:
    status = RemoteStatus.from_dict(
        {
            "device": "synthetic-device",
            "futureCloudField": "new-value",
        }
    )

    assert status.device == "synthetic-device"
    assert not hasattr(status, "futureCloudField")


def test_remote_status_ignores_unknown_unit_field() -> None:
    status = RemoteStatus.from_dict(
        {
            "cooler": [
                {
                    "name": "Common",
                    "zoneType": "COMMON",
                    "internal_temp": 22.0,
                    "futureUnitField": "new-value",
                }
            ]
        }
    )

    assert status.cooler == [UnitDetails(name="Common", zoneType="COMMON", internal_temp=22.0)]


def test_remote_status_converts_declared_nested_dataclass() -> None:
    status = RemoteStatus.from_dict({"installed": {"evap": True}})

    assert status.installed == Installed(evap=True)
    assert isinstance(status.installed, Installed)


def test_dataclass_from_dict_raises_for_missing_required_field() -> None:
    @dataclass
    class RequiredState:
        value: int

    with pytest.raises(TypeError):
        dataclass_from_dict(RequiredState, {})


@pytest.mark.parametrize("equipment", ["cooler", "heater"])
def test_remote_status_update_adds_new_unit(equipment: str, make_unit) -> None:
    common = make_unit()
    current = RemoteStatus(**{equipment: [common]})
    incoming_common = make_unit(internal_temp=23.0)
    incoming_zone = make_unit(
        name="Bedroom",
        zone_type="ZONE_1",
        internal_temp=21.0,
    )
    incoming = RemoteStatus(**{equipment: [incoming_common, incoming_zone]})

    current.update(incoming)

    units = getattr(current, equipment)
    assert units[0] is common
    assert units[0].internal_temp == 23.0
    assert units[1] is incoming_zone


@pytest.mark.parametrize("equipment", ["cooler", "heater"])
def test_remote_status_update_removes_missing_unit(equipment: str, make_unit) -> None:
    common = make_unit()
    removed_zone = make_unit(name="Bedroom", zone_type="ZONE_1")
    current = RemoteStatus(**{equipment: [common, removed_zone]})
    incoming = RemoteStatus(**{equipment: [make_unit(internal_temp=23.0)]})

    current.update(incoming)

    units = getattr(current, equipment)
    assert units == [common]
    assert units[0].internal_temp == 23.0


@pytest.mark.parametrize("equipment", ["cooler", "heater"])
def test_remote_status_update_reorders_by_stable_identity(equipment: str, make_unit) -> None:
    common = make_unit(internal_temp=20.0)
    bedroom = make_unit(name="Bedroom", zone_type="ZONE_1", internal_temp=21.0)
    current = RemoteStatus(**{equipment: [common, bedroom]})
    incoming = RemoteStatus(
        **{
            equipment: [
                make_unit(name="Bedroom", zone_type="ZONE_1", internal_temp=24.0),
                make_unit(internal_temp=23.0),
            ]
        }
    )

    current.update(incoming)

    units = getattr(current, equipment)
    assert units == [bedroom, common]
    assert units[0] is bedroom
    assert units[0].internal_temp == 24.0
    assert units[1] is common
    assert units[1].internal_temp == 23.0
