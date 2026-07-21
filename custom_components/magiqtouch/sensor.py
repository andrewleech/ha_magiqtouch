import logging

from . import MagIQtouchCoordinator
from .magiqtouch import MagIQtouch_Driver


# Import the device class from the component that you want to support
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import (
    DOMAIN,
    ZONE_COMMON,
    ZONE_NONE,
    is_valid_temperature,
)

_LOGGER = logging.getLogger("magiqtouch")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device based on a config entry."""
    driver: MagIQtouch_Driver = hass.data[DOMAIN][entry.entry_id]["driver"]
    coordinator: MagIQtouchCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    sensors = []

    sensors = [
        TemperatureSensor(
            "Temperature",
            driver,
            coordinator,
            zone=zone,
            data_callback=lambda z: driver.active_device(z).internal_temp,
        )
        for zone in driver.zone_list
    ]

    if driver.current_system_state.ExternalAirSensorPresent:
        sensors.append(
            TemperatureSensor(
                "External Temperature",
                driver,
                coordinator,
                data_callback=lambda z: driver.active_device(z).external_temp,
            )
        )
    # todo add zone temperature sensor etc
    async_add_entities(sensors, False)


class TemperatureSensor(CoordinatorEntity, SensorEntity):
    def __init__(
        self,
        label,
        controller: MagIQtouch_Driver,
        coordinator: MagIQtouchCoordinator,
        data_callback,
        zone=None,
    ):
        super().__init__(coordinator)
        self.label = label
        self.controller = controller
        self._attr_native_unit_of_measurement = controller.native_unit_of_measurement
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = {
            "identifiers": {("magiqtouch", self.controller.device_id)},
            "name": self.controller.device_name,
            "manufacturer": "Seeley",
            # "model": "<installed model>",
        }
        self.data_callback = data_callback
        self.zone = zone
        self.master_zone = (not self.zone) or self.zone in (ZONE_NONE, ZONE_COMMON)

        self._attr_native_value = None

    @property
    def name(self):
        """Return the name of the device."""
        if not self.master_zone:
            zone_name = self.controller.get_zone_name(self.zone)
            return f"{zone_name} - {self.label}"
        return f"{self.label}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("coordinator updated")
        try:
            value = self.data_callback(self.zone)
        except (AttributeError, IndexError, TypeError, ValueError) as ex:
            _LOGGER.debug("Temperature reading unavailable: %s", ex)
            value = None
        self._attr_native_value = (
            value if is_valid_temperature(value, self._attr_native_unit_of_measurement) else None
        )
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return whether the coordinator and this temperature reading are available."""
        return super().available and self._attr_native_value is not None

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        mac = self.controller.current_state.device
        zone_label = ""
        if self.zone and self.zone != ZONE_NONE:
            zone_name = self.controller.get_zone_name(self.zone).replace(" ", "-")
            zone_label = f"-zone-{zone_name}"
        uid = f"{mac}{zone_label}-sensor-{self.label}"
        return uid

    @property
    def should_poll(self) -> bool:
        return False
