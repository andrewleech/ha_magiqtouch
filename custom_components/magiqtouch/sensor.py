import logging

from . import MagiQtouchCoordinator
from .magiqtouch import MagiQtouch_Driver

from typing import Callable, List


# Import the device class from the component that you want to support
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from homeassistant.const import (
    UnitOfTemperature,
)
from .const import (
    # ATTR_IDENTIFIERS,
    # ATTR_MANUFACTURER,
    # ATTR_MODEL,
    # ATTR_TARGET_TEMPERATURE,
    DOMAIN,
)

_LOGGER = logging.getLogger("magiqtouch")


async def async_setup_entry(
    hass: HomeAssistantType,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[Entity], bool], None],
) -> None:
    """Set up device based on a config entry."""
    driver: MagiQtouch_Driver = hass.data[DOMAIN][entry.entry_id]["driver"]
    coordinator: MagiQtouchCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    sensors = []

    sensors = [
        TemperatureSensor(
            "Internal Temperature",
            driver,
            coordinator,
            zone=zone,
            data_callback=lambda z: driver.current_device_state(z).internal_temp,
        )
        for zone in driver.zone_list
    ]

    if driver.current_system_state.ExternalAirSensorPresent:
        sensors.append(
            TemperatureSensor(
                "External Temperature",
                driver,
                coordinator,
                data_callback=lambda z: driver.current_device_state(z).external_temp,
            )
        )
    # todo add zone temperature sensor etc
    async_add_entities(sensors, False)


class TemperatureSensor(CoordinatorEntity, SensorEntity):
    def __init__(
        self,
        label,
        controller: MagiQtouch_Driver,
        coordinator: MagiQtouchCoordinator,
        data_callback,
        zone=None,
    ):
        super().__init__(coordinator)
        self.label = label
        self.controller = controller
        self._attr_name = "MagiQtouch " + label
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self.data_callback = data_callback
        self.zone = zone

        self._attr_native_value = 0
        self._attr_available = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # self._attr_is_on = self.coordinator.data[self.idx]["state"]
        _LOGGER.debug("coordinator updated")
        self._attr_native_value = self.data_callback(self.zone)
        self._attr_available = True
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        mac = self.controller.current_state.device
        uid = f"{mac}-temperature-{self.label}"
        if self.zone:
            uid += f"-zone-{self.zone.replace(' ', '-')}"
        return uid

    # @property
    # def native_value(self) -> str:
    #     value = self.data_callback()
    #     _LOGGER.error(f"sensor read {value}")
    #     return value

    # @property
    # def available(self) -> bool:
    #     return True

    @property
    def should_poll(self) -> bool:
        return False
