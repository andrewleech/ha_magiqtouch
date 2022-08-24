"""Platform for climate integration."""
from datetime import timedelta
import logging

from .magiqtouch import MagiQtouch_Driver

import voluptuous as vol
from typing import Any, Callable, Dict, List, Optional
import homeassistant.helpers.config_validation as cv

# Import the device class from the component that you want to support
from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from homeassistant.components.climate.const import (
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_COOL,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_NONE,
    SUPPORT_FAN_MODE,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_DEVICES,
    CONF_PASSWORD,
    CONF_USERNAME,
    PRECISION_WHOLE,
    TEMP_CELSIUS,
)
from .const import (
    # ATTR_IDENTIFIERS,
    # ATTR_MANUFACTURER,
    # ATTR_MODEL,
    # ATTR_TARGET_TEMPERATURE,
    DOMAIN,
    FAN_MIN,
    FAN_MAX,
)

_LOGGER = logging.getLogger("magiqtouch")

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_FAN_MODE  # | SUPPORT_PRESET_MODE

HVAC_MODES = [HVAC_MODE_OFF, HVAC_MODE_COOL, HVAC_MODE_FAN_ONLY, HVAC_MODE_HEAT, HVAC_MODE_AUTO]

FAN_SPEED_AUTO = "auto"
FAN_SPEEDS = [str(spd+1) for spd in range(10)] + [FAN_SPEED_AUTO]


# def setup_platform(hass, config, add_entities, discovery_info=None):
#     """Set up the MagiQtouch platform."""
#     # Assign configuration variables.
#     # The configuration check takes care they are present.
#     username = config[CONF_USERNAME]
#     password = config.get(CONF_PASSWORD)
#
#     # Add devices
#     add_entities(MagiQtouch(username, password))

SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(
    hass: HomeAssistantType,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[Entity], bool], None],
) -> None:
    """Set up BSBLan device based on a config entry."""
    driver: MagiQtouch_Driver = hass.data[DOMAIN][entry.entry_id]
    await driver.login()
    await driver.initial_refresh(),
    if driver.current_system_state.NoOfZones == 0:
        async_add_entities([MagiQtouch(entry.entry_id, driver, 0)], True)
    else:
        async_add_entities([MagiQtouch(entry.entry_id, driver, i) for i in range(driver.current_system_state.NoOfZones)], True)


class MagiQtouch(ClimateEntity):
    """Representation of an Awesome Light."""

    def __init__(self, entry_id, controller: MagiQtouch_Driver, zone_index):
        """Initialize an AwesomeLight."""
        self.controller = controller
        self.controller.set_listener(self._updated)
        self.zone_index = zone_index
        # Best guess: generally if this is true, this zone is a "common zone" of some kind.
        self.controls_system = self.zone_index >= self.controller.current_system_state.NoOfZonesControl \
            or self.controller.current_system_state.NoOfZones == 0

    def _updated(self):
        self.schedule_update_ha_state(force_refresh=False)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def available(self) -> bool:
        """Return if thermostat is available."""
        return self.controller.logged_in

    @property
    def name(self):
        """Return the name of the device."""
        return self.controller.get_zone_name(self.zone_index) if self.controller.current_system_state.NoOfZones > 0 else "MagiQtouch"

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        id = self.controller.current_state.MacAddressId
        if self.controller.current_system_state.NoOfZones > 0:
            id += f"Zone{self.zone_index + 1}"
        return id

    @property
    def temperature_unit(self):
        """Return the unit of measurement that is used."""
        return TEMP_CELSIUS

    @property
    def precision(self):
        """Return unit precision as 1.0"""
        return PRECISION_WHOLE

    @property
    def target_temperature_step(self):
        return PRECISION_WHOLE
    
    @property
    def current_temperature(self):
        """Can not report temperature, so return target_temperature."""
        return self.controller.current_state.InternalTemp

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.controller.current_state.CTemp

    @property
    def max_temp(self):
        return self.controller.get_installed_device_config().get("MaximumTemperature", 35)

    @property
    def min_temp(self):
        return self.controller.get_installed_device_config().get("MinimumTemperature", 7)

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        # Heating temperature can only be changed across the entire system.
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self.controller.set_temperature(temperature)

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        on = self.controller.current_state.SystemOn
        if not on:
            _LOGGER.debug(HVAC_MODE_OFF)
            return HVAC_MODE_OFF
        # Show as off if individual zone is off
        zone_on = getattr(self.controller.current_state, self.controller.get_on_off_zone_name(self.zone_index))
        if not self.controls_system and not zone_on:
            _LOGGER.debug(HVAC_MODE_OFF)
            return HVAC_MODE_OFF
        fan_only = self.controller.current_state.CFanOnlyOrCool
        if fan_only:
            _LOGGER.debug(HVAC_MODE_FAN_ONLY)
            return HVAC_MODE_FAN_ONLY
        temperature_mode = self.controller.current_state.FanOrTempControl
        if temperature_mode:
            _LOGGER.debug(HVAC_MODE_COOL)
            return HVAC_MODE_COOL
        heating_running = self.controller.current_state.HRunning
        if heating_running:
            if self.controller.current_state.HFanOnly:
                _LOGGER.debug(HVAC_MODE_FAN_ONLY)
                return HVAC_MODE_FAN_ONLY
            _LOGGER.debug(HVAC_MODE_HEAT)
            return HVAC_MODE_HEAT
        # Cooling with fan speed
        _LOGGER.debug(HVAC_MODE_AUTO)
        return HVAC_MODE_AUTO

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        modes = [HVAC_MODE_OFF]
        if self.controller.current_system_state.HeaterInSystem == 1:
            modes.append(HVAC_MODE_HEAT)
            if self.controller.current_system_state.Heater.get("MaxSetFanSpeed", 0) > 0 and self.controls_system:
                modes.append(HVAC_MODE_FAN_ONLY)
            if self.controller.current_system_state.Heater.get("AOCInstalled", 0) == 1:
                modes.append(HVAC_MODE_COOL)
        if self.controller.current_system_state.AOCInverterInSystem == 1 \
            or self.controller.current_system_state.AOCFixedInSystem == 1 \
            or self.controller.current_system_state.NoOfEVAPInSystem > 0:
            modes.append(HVAC_MODE_COOL)
        return modes

    def set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        # This one gets confusing fast - each zone can be turned on and off individually,
        # but switching between heating vs fan mode applies only across the whole system.
        _LOGGER.debug("Set hvac_mode: %s" % hvac_mode)
        if hvac_mode == HVAC_MODE_OFF:
            if self.controls_system:
                self.controller.set_off()
            else:
                self.controller.set_zone_state(self.zone_index, False)
        elif hvac_mode == HVAC_MODE_FAN_ONLY:
            self.controller.set_fan_only()
        elif hvac_mode == HVAC_MODE_COOL:
            self.controller.set_cooling_by_temperature()
        elif hvac_mode == HVAC_MODE_HEAT:
            self.controller.set_heating()
        elif hvac_mode == HVAC_MODE_AUTO:
            self.controller.set_cooling_by_speed()
        else:
            _LOGGER.warning("Unknown hvac_mode: %s" % hvac_mode)
        # If we're not turning anything off, and this isn't a "whole system" zone, make sure this zone is on
        if not self.controls_system and hvac_mode != HVAC_MODE_OFF:
            self.controller.set_zone_state(self.zone_index, True)

    @property
    def fan_modes(self):
        """Return the supported fan modes."""
        return FAN_SPEEDS

    @property
    def fan_mode(self):
        """Return the current fan modes."""
        speed = str(self.controller.current_state.CFanSpeed)
        if speed == "0":
            return FAN_SPEED_AUTO
        return speed

    def set_fan_mode(self, mode):
        if mode == FAN_SPEED_AUTO:
            mode = 0

        elif str(mode) not in FAN_SPEEDS:
            _LOGGER.warning("Unknown fan speed: %s" % mode)

        else:
            _LOGGER.debug("Set fan to: %s" % mode)
            self.controller.set_current_speed(mode)

    # @property
    # def device_state_attributes(self):
    #     """Return the device specific state attributes."""
    #     ## TODO
    #     dev_specific = {
    #         ATTR_STATE_AWAY_END: self._thermostat.away_end,
    #         ATTR_STATE_LOCKED: self._thermostat.locked,
    #         ATTR_STATE_LOW_BAT: self._thermostat.low_battery,
    #         ATTR_STATE_VALVE: self._thermostat.valve_state,
    #         ATTR_STATE_WINDOW_OPEN: self._thermostat.window_open,
    #     }
    #
    #     return dev_specific

    # @property
    # def preset_mode(self):
    #     """Return the current preset mode, e.g., home, away, temp.
    #     Requires SUPPORT_PRESET_MODE.
    #     """
    #     return EQ_TO_HA_PRESET.get(self._thermostat.mode)
    #
    # @property
    # def preset_modes(self):
    #     """Return a list of available preset modes.
    #     Requires SUPPORT_PRESET_MODE.
    #     """
    #     return list(HA_TO_EQ_PRESET.keys())

    # def set_preset_mode(self, preset_mode):
    #     """Set new preset mode."""
    #     if preset_mode == PRESET_NONE:
    #         self.set_hvac_mode(HVAC_MODE_HEAT)
    #     self._thermostat.mode = HA_TO_EQ_PRESET[preset_mode]

    # def update(self):
    #     """Update the data from the thermostat."""
    #     try:
    #         self.controller.refresh_state()
    #     except Exception as ex:
    #         _LOGGER.warning("Updating the state failed: %s" % ex)

    async def async_update(self) -> None:
        """Update data entity."""
        try:
            await self.controller.refresh_state()
        except Exception as ex:
            _LOGGER.warning("Updating the state failed: %s(%s)" % (type(ex), ex))
            await self.controller.login()
