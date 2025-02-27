"""The Seeley MagiQtouch integration."""
import sys
from pathlib import Path

__vendor__ = str(Path(__file__).parent / "vendor")
sys.path.append(__vendor__)

import logging
import asyncio

import voluptuous as vol

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
from .magiqtouch import MagiQtouch_Driver
from .const import (
    SCAN_INTERVAL,
    DOMAIN,
    CONF,
    ZoneType,
)
from .structures import SystemDetails, RemoteStatus
from homeassistant.const import Platform

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

# List the platforms that you want to support.
PLATFORMS = [
    CLIMATE_DOMAIN,
    Platform.SENSOR,
]

_LOGGER = logging.getLogger("magiqtouch")


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Seeley MagiQtouch component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Seeley MagiQtouch from a config entry."""
    username = entry.data[CONF.USERNAME]
    password = entry.data[CONF.PASSWORD]

    driver = MagiQtouch_Driver(
        user=username,
        password=password,
        hass=hass,
        config_entry=entry,
    )
    coordinator = MagiQtouchCoordinator(hass, driver)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = dict(
        driver=driver,
        coordinator=coordinator,
    )

    driver.set_verbose(entry.options.get(CONF.VERBOSE, False), initial=True)

    if state := entry.data.get(CONF.SYS_STATE):
        driver.set_system_state(SystemDetails.from_dict(state))
    else:
        _LOGGER.warning("CONF.SYS_STATE missing")
        await driver.full_refresh(initial=True)

    if zones := entry.data.get(CONF.ZONES):
        driver.zone_list = [ZoneType(*cz) for cz in zones]
    else:
        _LOGGER.warning("CONF.ZONES missing")
        await driver.full_refresh(initial=True)

    if state := entry.data.get(CONF.STATE):
        driver.current_state = RemoteStatus.from_dict(state)
        driver.current_state.runningMode != ""
    else:
        _LOGGER.warning("CONF.STATE missing")
        await driver.full_refresh(initial=True)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # listen for changes to the configuration options
    entry.async_on_unload(entry.add_update_listener(options_update_listener))
    return True


async def options_update_listener(hass, config_entry):
    """Handle options update."""
    driver = hass.data[DOMAIN][config_entry.entry_id]["driver"]
    driver.set_verbose(config_entry.options.get(CONF.VERBOSE, False))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    driver = hass.data[DOMAIN][entry.entry_id]["driver"]
    await driver.logout()

    return unload_ok


class MagiQtouchCoordinator(DataUpdateCoordinator):
    """An update coordinator that handles updates for the entire MagiQtouch integration."""

    controller: MagiQtouch_Driver

    def __init__(self, hass, controller):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="MagiQtouch",
            update_interval=SCAN_INTERVAL,
        )
        self.controller = controller
        self.controller.set_listener(self.data_updated)

    def data_updated(self):
        self.async_set_updated_data(None)

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        Data should be pre-processed here if possible.
        For more info, see https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
        """
        try:
            return await self.controller.refresh_state()
        except Exception as ex:
            _LOGGER.warning(
                "Updating the state failed, will retry with login: %s(%s)" % (type(ex), ex)
            )
            await self.controller.login()
