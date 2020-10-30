"""Platform for climate integration."""
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

HVAC_MODES = [HVAC_MODE_OFF, HVAC_MODE_COOL, HVAC_MODE_FAN_ONLY, HVAC_MODE_AUTO]

FAN_SPEEDS = [(FAN_LOW, 2), (FAN_MEDIUM, 5), (FAN_HIGH, 10)]


# def setup_platform(hass, config, add_entities, discovery_info=None):
#     """Set up the MagiQtouch platform."""
#     # Assign configuration variables.
#     # The configuration check takes care they are present.
#     username = config[CONF_USERNAME]
#     password = config.get(CONF_PASSWORD)
#
#     # Add devices
#     add_entities(MagiQtouch(username, password))


async def async_setup_entry(
    hass: HomeAssistantType,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[Entity], bool], None],
) -> None:
    """Set up BSBLan device based on a config entry."""
    driver: MagiQtouch_Driver = hass.data[DOMAIN][entry.entry_id]
    await driver.login()
    await hass.async_add_executor_job(
        driver.mqtt_connect,
    )
    async_add_entities([MagiQtouch(entry.entry_id, driver)], True)


class MagiQtouch(ClimateEntity):
    """Representation of an Awesome Light."""

    def __init__(self, entry_id, controller: MagiQtouch_Driver):
        """Initialize an AwesomeLight."""
        self.controller = controller
        self.controller.set_listener(self._updated)

        # self.controller.mqtt_connect()

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
        return "MagiQtouch"

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        return self.controller.current_state.MacAddressId

    @property
    def temperature_unit(self):
        """Return the unit of measurement that is used."""
        return TEMP_CELSIUS

    @property
    def precision(self):
        """Return eq3bt's precision 0.5."""
        return PRECISION_WHOLE

    @property
    def current_temperature(self):
        """Can not report temperature, so return target_temperature."""
        return self.controller.current_state.InternalTemp

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.controller.current_state.CTemp

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self.controller.set_temperature(temperature)

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        on = self.controller.current_state.SystemOn
        if not on:
            return HVAC_MODE_OFF
        fan_only = self.controller.current_state.CFanOnlyOrCool
        if fan_only:
            return HVAC_MODE_FAN_ONLY
        temperature_mode = self.controller.current_state.FanOrTempControl
        if temperature_mode:
            return HVAC_MODE_AUTO
        return HVAC_MODE_COOL

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return HVAC_MODES

    def set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        # if self.preset_mode:
        #     return
        if hvac_mode == HVAC_MODE_OFF:
            self.controller.set_off()
        elif hvac_mode == HVAC_MODE_FAN_ONLY:
            self.controller.set_fan_only()
        elif hvac_mode == HVAC_MODE_COOL:
            self.controller.set_cooling()

    @property
    def fan_modes(self):
        """Return the supported fan modes."""
        return [FAN_LOW, FAN_MEDIUM, FAN_HIGH]

    @property
    def fan_mode(self):
        """Return the current fan modes."""
        speed = self.controller.current_state.CFanSpeed
        for mode, level in FAN_SPEEDS:
            if speed <= level:
                return mode
        return FAN_LOW

    def set_fan_mode(self, mode):
        speed = dict(FAN_SPEEDS).get(mode, None)
        if speed is None:
            _LOGGER.warning("Unknown mode: %s" % mode)

        else:
            self.controller.set_current_speed(speed)


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

    def update(self):
        """Update the data from the thermostat."""
        try:
            self.controller.refresh_state()
        except Exception as ex:
            _LOGGER.warning("Updating the state failed: %s" % ex)

    async def async_update(self) -> None:
        """Update BSBlan entity."""