"""Platform for climate integration."""
import logging

from . import MagiQtouchCoordinator
from .magiqtouch import MagiQtouch_Driver

import voluptuous as vol
from typing import Callable, List
import homeassistant.helpers.config_validation as cv


# Import the device class from the component that you want to support
from homeassistant.components.climate import (
    PLATFORM_SCHEMA,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from homeassistant.components.climate.const import (
    PRESET_NONE,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
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
    MODE_COOLER,
    MODE_COOLER_FAN,
    MODE_HEATER,
    MODE_HEATER_FAN,
    CONTROL_MODE_TEMP,
)

_LOGGER = logging.getLogger("magiqtouch")


# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

SUPPORT_FLAGS = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.PRESET_MODE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)

HVAC_MODES = [HVACMode.OFF, HVACMode.COOL, HVACMode.FAN_ONLY, HVACMode.HEAT]

FAN_SPEED_BY_TEMP = "Temperature"
FAN_SPEED_TO_PREV = "Previous"
FAN_SPEEDS = [FAN_SPEED_BY_TEMP, FAN_SPEED_TO_PREV] + [str(spd + 1) for spd in range(10)]

PRESET_FAN_FRESH = "Fan: Fresh Air"
PRESET_FAN_RECIRC = "Fan: Recirculate"
PRESET_EVAP_TEMP = "Evaporative: set temperature"
PRESET_EVAP_FAN_SPEED = "Evaporative: set fan speed"
PRESET_HEAT_TEMP = "Heating: set temperature"
PRESET_HEAT_FAN_SPEED = "Heating: set fan speed"
PRESET_COOL_TEMP = "Cooling: set temperature"
PRESET_COOL_FAN_SPEED = "Cooling: set fan speed"


async def async_setup_entry(
    hass: HomeAssistantType,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[Entity], bool], None],
) -> None:
    """Set up device based on a config entry."""
    driver: MagiQtouch_Driver = hass.data[DOMAIN][entry.entry_id]["driver"]
    coordinator: MagiQtouchCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    if True or driver.current_system_state.NoOfZoneControls == 0:
        # No zones, just the one system entity
        async_add_entities([MagiQtouch(entry.entry_id, driver, coordinator)], False)
    else:
        # create one entity per zone
        async_add_entities(
            [
                MagiQtouch(entry.entry_id, driver, coordinator, i)
                for i in range(driver.current_system_state.NoOfZoneControls)
            ],
            False,
        )


class MagiQtouch(CoordinatorEntity, ClimateEntity):
    """Representation of an MagIQtouch Thermostat."""

    def __init__(
        self,
        entry_id,
        controller: MagiQtouch_Driver,
        coordinator: MagiQtouchCoordinator,
        zone_id=None,
    ):
        self._attr_name = "MagiQtouch"
        super().__init__(coordinator)
        self.controller = controller
        self.zone_id = zone_id
        self.coordinator = coordinator
        # Best guess: generally if this is true, this zone is a "common zone" of some kind.
        self.zone_entity = zone_id is not None
        # https://developers.home-assistant.io/blog/2024/01/24/climate-climateentityfeatures-expanded/
        self._enable_turn_on_off_backwards_compatibility = False

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def available(self) -> bool:
        """Return if thermostat is available."""
        return (
            self.controller.logged_in
            and self.controller.ws is not None
            and self.controller.current_state.runningMode is not None
        )

    @property
    def name(self):
        """Return the name of the device."""
        return (
            self.controller.get_zone_name(self.zone_id)
            if self.controller.current_system_state.NoOfZoneControls > 0
            else "MagiQtouch"
        )

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        uid = self.controller.current_state.device
        if self.controller.current_system_state.NoOfZoneControls > 0:
            uid += f"Zone{self.zone_id + 1}"
        return uid

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
        return self.controller.current_device_state.internal_temp

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.controller.current_device_state.set_temp

    @property
    def max_temp(self):
        try:
            return self.controller.current_device_state.max_temp
        except:
            return 35

    @property
    def min_temp(self):
        try:
            return self.controller.current_device_state.mim_temp
        except:
            return 7

    async def async_turn_on(self):
        await self.controller.set_on()

    async def async_turn_off(self):
        await self.controller.set_off()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        # Heating temperature can only be changed across the entire system.
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.controller.set_temperature(temperature)

    @property
    def hvac_action(self):
        on = self.controller.current_state.systemOn
        if not on:
            _LOGGER.debug(HVACAction.OFF)
            return HVACAction.OFF

        ## todo zones
        # Show as off if individual zone is off
        # zone_on = getattr(
        #     self.controller.current_state,
        #     self.controller.get_on_off_zone_name(self.zone_id),
        # )
        # if self.zone_entity and not zone_on:
        #     _LOGGER.debug(HVACAction.OFF + " (zone)")
        #     return HVACAction.OFF
        runningMode = self.controller.current_state.runningMode
        hvac_action = {
            MODE_COOLER: HVACAction.COOLING,
            MODE_HEATER: HVACAction.HEATING,
            MODE_COOLER_FAN: HVACAction.FAN,
            MODE_HEATER_FAN: HVACAction.FAN,
        }.get(runningMode, HVACAction.IDLE)

        _LOGGER.debug("runningMode: %s, hvac_action: %s", runningMode, hvac_action)
        return hvac_action

        # if (
        #     self.controller.current_state.HActualGasRate > 0
        #     and self.controller.current_state.HActualFanSpeed > 0
        # ):
        #     return HVACAction.HEAT
        # elif (
        #     self.controller.current_state.HFanOnly == 1
        #     and self.controller.current_state.HActualFanSpeed > 0
        #     and self.controller.current_state.HFanSpeed > 0
        # ) or self.controller.current_state.CFanOnlyOrCool == 1:
        #     return HVACAction.FAN
        # elif (
        #     self.controller.current_state.FAOCActualCompressorON == 1
        #     or self.controller.current_state.IAOCCompressorON == 1
        #     or (
        #         self.controller.current_state.EvapCRunning
        #         and self.controller.current_state.PumpStatus
        #     )
        # ):
        #     return HVACAction.COOL
        # else:
        #     return HVACAction.IDLE

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        on = self.controller.current_state.systemOn
        if not on:
            _LOGGER.debug(f"hvac_mode: {HVACMode.OFF}")
            return HVACMode.OFF
        # todo zones
        # Show as off if individual zone is off
        # zone_on = getattr(
        #     self.controller.current_state,
        #     self.controller.get_on_off_zone_name(self.zone_id),
        # )
        # if self.zone_entity and not zone_on:
        #     _LOGGER.debug(f"hvac_mode: (individual zone) {HVACMode.OFF}")
        #     return HVACMode.OFF

        runningMode = self.controller.current_state.runningMode
        hvac_mode = {
            MODE_COOLER: HVACMode.COOL,
            MODE_HEATER: HVACMode.HEAT,
            MODE_COOLER_FAN: HVACMode.FAN_ONLY,
            MODE_HEATER_FAN: HVACMode.FAN_ONLY,
        }.get(runningMode, HVACMode.OFF)

        _LOGGER.debug("runningMode: %s, hvac_mode: %s", runningMode, hvac_mode)
        return hvac_mode

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""

        modes = [HVACMode.OFF, HVACMode.FAN_ONLY]
        system = self.controller.current_system_state.System
        if system.heater.available:
            modes.append(HVACMode.HEAT)
        if system.cooler.available:
            modes.append(HVACMode.COOL)

        # if (
        #     self.controller.current_system_state.installed.iaoc
        #     or self.controller.current_system_state.installed.faoc
        #     or self.controller.current_system_state.installed.evap
        # ):
        #     modes.append(HVACMode.COOL)

        return modes

    async def async_set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        # This one gets confusing fast - each zone can be turned on and off individually,
        # but switching between heating vs fan mode applies only across the whole system.
        _LOGGER.debug("Set hvac_mode: %s" % hvac_mode)
        if hvac_mode == HVACMode.OFF:
            if not self.zone_entity:
                await self.controller.set_off()
            else:
                await self.controller.set_zone_state(self.zone_id, False)
        elif hvac_mode == HVACMode.FAN_ONLY:
            await self.controller.set_fan_only()
        elif hvac_mode == HVACMode.COOL:
            if (
                self.controller.current_state.installed.faoc
                or self.controller.current_state.installed.iaoc
            ):
                await self.controller.set_add_on_cooler()
            else:
                await self.controller.set_cooling()
        elif hvac_mode == HVACMode.HEAT:
            await self.controller.set_heating()
        else:
            _LOGGER.warning("Unknown hvac_mode: %s" % hvac_mode)
        # If we're not turning anything off, and this isn't a "whole system" zone,
        # make sure this zone is on
        if self.zone_id and hvac_mode != HVACMode.OFF:
            await self.controller.set_zone_state(self.zone_id, True)

        await self.coordinator.async_request_refresh()

    @property
    def fan_modes(self):
        """Return the supported fan modes."""
        return FAN_SPEEDS

    @property
    def fan_mode(self):
        """Return the current fan modes."""
        if self.controller.current_device_state.control_mode == CONTROL_MODE_TEMP:
            # running in temperature set point mode
            return FAN_SPEED_BY_TEMP
        speed = str(self.controller.current_device_state.fan_speed)
        if speed == "0":
            return FAN_SPEED_BY_TEMP
        return speed

    async def async_set_fan_mode(self, fan_mode):
        if str(fan_mode) not in FAN_SPEEDS:
            _LOGGER.warning("Unknown fan speed: %s" % fan_mode)
        else:
            _LOGGER.debug("Set fan to: %s" % fan_mode)
            if fan_mode == FAN_SPEED_BY_TEMP:
                await self.controller.set_cooling_by_temperature()
            elif fan_mode == FAN_SPEED_TO_PREV:
                await self.controller.set_cooling_by_speed()
            else:
                await self.controller.set_current_speed(fan_mode)

        await self.coordinator.async_request_refresh()

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

    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., home, away, temp.
        Requires SUPPORT_PRESET_MODE.
        """
        runningMode = self.controller.current_state.runningMode
        if runningMode == MODE_HEATER_FAN:
            return PRESET_FAN_RECIRC
        elif runningMode == MODE_COOLER_FAN:
            return PRESET_FAN_FRESH

        temperature_mode = self.controller.current_device_state.control_mode == CONTROL_MODE_TEMP
        evap_cooling_mode = self.controller.current_state.runningMode == MODE_COOLER
        if evap_cooling_mode:
            if temperature_mode:
                return PRESET_EVAP_TEMP
            return PRESET_EVAP_FAN_SPEED
        heating_running = self.controller.current_state.runningMode == MODE_HEATER
        if heating_running:
            if temperature_mode:
                return PRESET_HEAT_TEMP
            return PRESET_HEAT_FAN_SPEED
        return PRESET_NONE

    @property
    def preset_modes(self):
        """Return a list of available preset modes.
        Requires SUPPORT_PRESET_MODE.
        """
        presets = [PRESET_NONE]
        sys_state = self.controller.current_system_state
        if sys_state.Heater.InSystem:
            presets.extend(
                [
                    PRESET_HEAT_TEMP,
                    PRESET_HEAT_FAN_SPEED,
                    PRESET_FAN_RECIRC,
                ]
            )
            # todo was previously:
            # if sys_state.Heater.get("AOCInstalled", 0) > 0:
            if sys_state.AOCFixed.InSystem or sys_state.AOCInverter.InSystem:
                presets.extend(
                    [
                        PRESET_COOL_TEMP,
                        PRESET_COOL_FAN_SPEED,
                    ]
                )
        # todo: figure better evap detection
        # self.controller.current_state.installed.evap:
        if sys_state.System.cooler.available:
            presets.extend(
                [
                    PRESET_EVAP_TEMP,
                    PRESET_EVAP_FAN_SPEED,
                    PRESET_FAN_FRESH,
                ]
            )
        return presets

    async def async_set_preset_mode(self, preset_mode):
        """Set new preset mode."""
        if preset_mode == PRESET_FAN_FRESH:
            await self.controller.set_fan_only_evap()
        elif preset_mode == PRESET_FAN_RECIRC:
            await self.controller.set_fan_only_heater()
        elif preset_mode == PRESET_EVAP_TEMP:
            await self.controller.set_cooling_by_temperature()
        elif preset_mode == PRESET_EVAP_FAN_SPEED:
            await self.controller.set_cooling_by_speed()
        elif preset_mode == PRESET_HEAT_TEMP:
            await self.controller.set_heating_by_temperature()
        elif preset_mode == PRESET_HEAT_FAN_SPEED:
            await self.controller.set_heating_by_speed()
        elif preset_mode == PRESET_COOL_TEMP:
            await self.controller.set_aoc_by_temperature()
        elif preset_mode == PRESET_COOL_FAN_SPEED:
            await self.controller.set_aoc_by_speed()
        elif preset_mode == PRESET_NONE:
            await self.async_set_hvac_mode(HVACMode.OFF)
        # self._thermostat.mode = HA_TO_EQ_PRESET[preset_mode]

    # def update(self):
    #     """Update the data from the thermostat."""
    #     try:
    #         self.controller.refresh_state()
    #     except Exception as ex:
    #         _LOGGER.warning("Updating the state failed: %s" % ex)
