"""Platform for climate integration."""
import logging

from . import MagiQtouchCoordinator
from .magiqtouch import MagiQtouch_Driver
from .structures import UnitDetails

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
    UnitOfTemperature,
)
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    ZONE_TYPE_COMMON,
    ZONE_TYPE_NONE,
)

_LOGGER = logging.getLogger("magiqtouch")


# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

HVAC_MODES = [HVACMode.OFF, HVACMode.COOL, HVACMode.FAN_ONLY, HVACMode.HEAT]

FAN_SPEED_BY_TEMP = "Temperature"
FAN_SPEED_TO_PREV = "Previous"
FAN_SPEEDS = [FAN_SPEED_BY_TEMP, FAN_SPEED_TO_PREV] + [str(spd + 1) for spd in range(10)]

PRESET_FAN_FRESH = "Fan: Fresh Air"
PRESET_FAN_RECIRC = "Fan: Recirculate"
# PRESET_EVAP_TEMP = "Evaporative: set temperature"
# PRESET_EVAP_FAN_SPEED = "Evaporative: set fan speed"
PRESET_HEAT_TEMP = "Heating: set temperature"
PRESET_HEAT_FAN_SPEED = "Heating: set fan speed"
PRESET_COOL_TEMP = "Cooling: set temperature"
PRESET_COOL_FAN_SPEED = "Cooling: set fan speed"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[Entity], bool], None],
) -> None:
    """Set up device based on a config entry."""
    driver: MagiQtouch_Driver = hass.data[DOMAIN][entry.entry_id]["driver"]
    coordinator: MagiQtouchCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities(
        [MagiQtouch(entry.entry_id, driver, coordinator, zone) for zone in driver.zone_list], False
    )


class MagiQtouch(CoordinatorEntity, ClimateEntity):
    """Representation of an MagIQtouch Thermostat."""

    def __init__(
        self,
        entry_id,
        controller: MagiQtouch_Driver,
        coordinator: MagiQtouchCoordinator,
        zone=None,
    ):
        self._attr_name = "MagiQtouch"
        super().__init__(coordinator)
        self.controller = controller
        self.coordinator = coordinator

        self.zone = zone
        self.master_zone = (not self.zone) or self.zone in (ZONE_TYPE_NONE, ZONE_TYPE_COMMON)

        self.master_mode_only_controller = False
        self._cooler: list[UnitDetails] = []
        self._heater: list[UnitDetails] = []

        # https://developers.home-assistant.io/blog/2024/01/24/climate-climateentityfeatures-expanded/
        self._enable_turn_on_off_backwards_compatibility = False

    @property
    def name(self):
        """Return the name of the device."""
        if not self.master_zone:
            return f"MagiQtouch - {self.controller.get_zone_name(self.zone)}"
        return "MagiQtouch"

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        uid = self.controller.current_state.device
        if not self.master_zone:
            zone_name = self.controller.get_zone_name(self.zone).replace(" ", "-")
            uid += f"-zone-{zone_name}"
        return uid

    def _init_units(self):
        if not self.available:
            raise ValueError("Not available yet")
        self._cooler = self.controller.available_coolers(self.zone)
        self._heater = self.controller.available_heaters(self.zone)
        self.master_mode_only_controller = not (self._cooler or self._heater)
        if self.master_mode_only_controller:
            self._cooler = self.controller.current_state.cooler
            self._heater = self.controller.current_state.heater

    @property
    def cooler(self):
        if not self._cooler:
            self._init_units()
        return self._cooler

    @property
    def heater(self):
        if not self._heater:
            self._init_units()
        return self._heater

    @property
    def supported_features(self):
        """Return the list of supported features for this entity."""
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self.master_zone:
            features |= ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.PRESET_MODE
        if not self.master_mode_only_controller:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        return features

    @property
    def available(self) -> bool:
        """Return if thermostat is available."""
        return (
            self.controller.logged_in
            and self.controller.jobs is not None
            and self.controller.current_state.runningMode != ""
        )

    @property
    def active_units(self):
        state = self.controller.current_state
        if state.runningMode in (MODE_COOLER, MODE_COOLER_FAN):
            return self.cooler
        elif state.runningMode in (MODE_HEATER, MODE_HEATER_FAN):
            return self.heater
        else:
            return []

    @property
    def inactive_units(self):
        state = self.controller.current_state
        if state.runningMode in (MODE_COOLER, MODE_COOLER_FAN):
            return self.heater
        elif state.runningMode in (MODE_HEATER, MODE_HEATER_FAN):
            return self.cooler
        else:
            return []

    @property
    def temperature_unit(self):
        """Return the unit of measurement that is used."""
        return UnitOfTemperature.CELSIUS

    @property
    def precision(self):
        """Return unit precision as 1.0"""
        return PRECISION_WHOLE

    @property
    def target_temperature_step(self):
        return PRECISION_WHOLE

    @property
    def current_temperature(self):
        units = self.active_units or self.inactive_units
        if len(units) > 1:
            itemps = [u.internal_temp for u in units if u.internal_temp < 100]
            current = sum(itemps) / len(itemps)
        else:
            current = units[0].internal_temp
        if current > 100:
            # No sensor
            try:
                # report common zone if it exists
                current = self.controller.active_device(ZONE_TYPE_COMMON).internal_temp
            except:
                current = self.target_temperature
        return current

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        units = self.active_units or self.inactive_units
        return units[0].set_temp
        # return self.controller.active_device(self.zone).set_temp

    @property
    def max_temp(self):
        if not self.available:
            return 35
        units = self.active_units or self.inactive_units
        return units[0].max_temp
        # try:
        #     return self.controller.active_device(self.zone).max_temp
        # except:
        #     return 35

    @property
    def min_temp(self):
        if not self.available:
            return 7
        units = self.active_units or self.inactive_units
        return units[0].min_temp
        # try:
        #     return self.controller.active_device(self.zone).min_temp
        # except:
        #     return 7

    async def async_turn_on(self):
        # If turning any zone on, ensure system is on
        await self.controller.set_on()
        if not self.master_zone:
            await self.controller.set_zone_onoff(self.zone, True)

    async def async_turn_off(self):
        if self.master_zone:
            await self.controller.set_off()
        else:
            await self.controller.set_zone_onoff(self.zone, False)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        # Heating temperature can only be changed across the entire system.
        if self.master_mode_only_controller:
            return
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.controller.set_temperature(temperature, zone=self.zone)

    @property
    def hvac_action(self):
        on = self.controller.current_state.systemOn
        if not on:
            _LOGGER.debug(HVACAction.OFF)
            return HVACAction.OFF

        # Show as off if individual zone is off
        if (not self.master_mode_only_controller) and self.zone and self.zone != ZONE_TYPE_NONE:
            zone_on = self.controller.get_zone_onoff(self.zone)
            if not zone_on:
                _LOGGER.debug(HVACAction.OFF + " (zone)")
                return HVACAction.OFF
            elif not self.active_units:
                # eg. heating mode in cool-only zones
                return HVACAction.IDLE

        runningMode = self.controller.current_state.runningMode
        hvac_action = {
            MODE_COOLER: HVACAction.COOLING,
            MODE_HEATER: HVACAction.HEATING,
            MODE_COOLER_FAN: HVACAction.FAN,
            MODE_HEATER_FAN: HVACAction.FAN,
        }.get(runningMode, HVACAction.IDLE)

        _LOGGER.debug("runningMode: %s, hvac_action: %s", runningMode, hvac_action)

        # if hvac_action not in self.hvac_actions:
        #     _LOGGER.warning("hvac_action not sorted by zone, returning idle")
        #     hvac_action = HVACAction.IDLE

        return hvac_action

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        on = self.controller.current_state.systemOn
        if not on:
            _LOGGER.debug(f"hvac_mode: {HVACMode.OFF}")
            return HVACMode.OFF

        if (not self.master_mode_only_controller) and self.zone and self.zone != ZONE_TYPE_NONE:
            zone_on = self.controller.get_zone_onoff(self.zone)
            if not zone_on:
                _LOGGER.debug(HVACAction.OFF + " (zone)")
                return HVACMode.OFF
            elif not self.active_units:
                # eg. heating mode in cool-only zones
                return HVACMode.OFF

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
        modes = [HVACMode.OFF]

        if self.master_zone:
            modes.append(HVACMode.FAN_ONLY)
            if self.heater:
                modes.append(HVACMode.HEAT)
            if self.cooler:
                modes.append(HVACMode.COOL)
        else:
            # individual zone controllers
            if self.available:
                state = self.controller.current_state
                if state.runningMode == MODE_COOLER:
                    modes.append(HVACMode.COOL)
                elif state.runningMode == MODE_HEATER:
                    modes.append(HVACMode.HEAT)
                elif state.runningMode in (MODE_COOLER_FAN, MODE_HEATER_FAN):
                    modes.append(HVACMode.FAN_ONLY)
            else:
                modes.append(HVACMode.AUTO)

        _LOGGER.debug(f"hvac_modes: {modes}")
        return modes

    async def async_set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        # This one gets confusing fast - each zone can be turned on and off individually,
        # but switching between heating vs fan mode applies only across the whole system.
        _LOGGER.debug("Set hvac_mode: %s" % hvac_mode)
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()

        elif self.master_zone:
            if hvac_mode == HVACMode.FAN_ONLY:
                await self.controller.set_fan_only(self.zone)
            elif hvac_mode == HVACMode.COOL:
                # if (
                #     self.controller.current_state.installed.faoc
                #     or self.controller.current_state.installed.iaoc
                # ):
                #     await self.controller.set_add_on_cooler()
                # else:
                await self.controller.set_cooling(self.zone)
            elif hvac_mode == HVACMode.HEAT:
                await self.controller.set_heating(self.zone)
            else:
                _LOGGER.error("Unknown hvac_mode: %s" % hvac_mode)
        # If we're not turning anything off, and this isn't a "whole system" zone,
        # make sure this zone is on
        if hvac_mode != HVACMode.OFF:
            await self.async_turn_on()

        await self.coordinator.async_request_refresh()

    @property
    def fan_modes(self):
        """Return the supported fan modes."""
        return FAN_SPEEDS

    @property
    def fan_mode(self):
        """Return the current fan modes."""
        if self.controller.active_device(self.zone).control_mode == CONTROL_MODE_TEMP:
            # running in temperature set point mode
            return FAN_SPEED_BY_TEMP
        speed = str(self.controller.active_device(self.zone).fan_speed)
        if speed == "0":
            return FAN_SPEED_BY_TEMP
        return speed

    async def async_set_fan_mode(self, fan_mode):
        if str(fan_mode) not in FAN_SPEEDS:
            _LOGGER.warning("Unknown fan speed: %s" % fan_mode)
        else:
            _LOGGER.debug("Set fan to: %s" % fan_mode)
            if fan_mode == FAN_SPEED_BY_TEMP:
                await self.controller.set_cooling_by_temperature(self.zone)
            elif fan_mode == FAN_SPEED_TO_PREV:
                await self.controller.set_cooling_by_speed(self.zone)
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

        temperature_mode = (
            self.controller.active_device(self.zone).control_mode == CONTROL_MODE_TEMP
        )
        cooling_mode = self.controller.current_state.runningMode == MODE_COOLER
        if cooling_mode:
            if temperature_mode:
                return PRESET_COOL_TEMP
            return PRESET_COOL_FAN_SPEED
        heating_mode = self.controller.current_state.runningMode == MODE_HEATER
        if heating_mode:
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
        cur_state = self.controller.current_state
        # sys_state = self.controller.current_system_state
        # if sys_state.Heater.InSystem:
        if self.controller.available_heaters(self.zone):
            presets.append(PRESET_HEAT_TEMP)
            # presets.append(PRESET_HEAT_FAN_SPEED)
            if cur_state.fan.heater_available:
                presets.append(PRESET_FAN_RECIRC)

        # todo AOC
        # if sys_state.Heater.get("AOCInstalled", 0) > 0:
        # if sys_state.System.cooler.available or sys_state.AOCFixed.InSystem
        #        or sys_state.AOCInverter.InSystem:
        if self.controller.available_coolers(self.zone):
            presets.append(PRESET_COOL_TEMP)
            if self.controller.current_state.installed.evap:
                presets.append(PRESET_COOL_FAN_SPEED)
            if cur_state.fan.cooler_available:
                presets.append(PRESET_FAN_FRESH)

        return presets

    async def async_set_preset_mode(self, preset_mode):
        """Set new preset mode."""
        if preset_mode == PRESET_FAN_FRESH:
            await self.controller.set_fan_only_evap(self.zone)
        elif preset_mode == PRESET_FAN_RECIRC:
            await self.controller.set_fan_only_heater(self.zone)
        elif preset_mode == PRESET_COOL_TEMP:
            await self.controller.set_cooling_by_temperature(self.zone)
        elif preset_mode == PRESET_COOL_FAN_SPEED:
            await self.controller.set_cooling_by_speed(self.zone)
        elif preset_mode == PRESET_HEAT_TEMP:
            await self.controller.set_heating_by_temperature(self.zone)
        elif preset_mode == PRESET_HEAT_FAN_SPEED:
            await self.controller.set_heating_by_speed(self.zone)
        # elif preset_mode == PRESET_COOL_TEMP:
        #     await self.controller.set_aoc_by_temperature(self.zone)
        # elif preset_mode == PRESET_COOL_FAN_SPEED:
        #     await self.controller.set_aoc_by_speed(self.zone)
        elif preset_mode == PRESET_NONE:
            await self.async_set_hvac_mode(HVACMode.OFF)
