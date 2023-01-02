"""The Seeley MagiQtouch integration."""
import sys
import async_timeout
from pathlib import Path
from datetime import timedelta

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
    CONF_VERBOSE,
)
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)

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
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    driver = MagiQtouch_Driver(user=username, password=password)
    coordinator = MagiQtouchCoordinator(hass, driver)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = dict(
        driver=driver,
        coordinator=coordinator,
    )
    driver.set_verbose(entry.options.get(CONF_VERBOSE, False), initial=True)

    await driver.login(hass)

    # try:
    #     success = await driver.login(hass)
    #     if not success:
    #         raise ConfigEntryNotReady
    # except Exception as exception:
    #     raise ConfigEntryNotReady from exception

    # await driver.login(hass)
    # await driver.initial_refresh()
    # await coordinator.async_config_entry_first_refresh()

    for component in PLATFORMS:
        hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, component))
    # listen for changes to the configuration options
    entry.async_on_unload(entry.add_update_listener(options_update_listener))
    return True


async def options_update_listener(hass, config_entry):
    """Handle options update."""
    driver = hass.data[DOMAIN][config_entry.entry_id]["driver"]
    driver.set_verbose(config_entry.options[CONF_VERBOSE])


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
    if unload_ok:
        driver = hass.data[DOMAIN][entry.entry_id]["driver"]
        driver.logout()

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
        self.fast_update = 0
        self.controller.set_listener(self.data_updated)

    def data_updated(self):
        self.async_set_updated_data(None)

    def start_fast_updates(self):
        """fetch data at high polling rate for 8 second"""
        _LOGGER.debug("start fast update")
        self.fast_update = 16
        self.update_interval = timedelta(milliseconds=500)

    async def async_request_refresh(self):
        self.start_fast_updates()
        return await super().async_request_refresh()

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        Data should be pre-processed here if possible.
        For more info, see https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
        """
        if self.fast_update:
            _LOGGER.debug("fast refresh")
            self.fast_update -= 1
            if not self.fast_update:
                self.update_interval = SCAN_INTERVAL

        try:
            async with async_timeout.timeout(10):
                return await self.controller.refresh_state()
        except Exception as ex:
            _LOGGER.warning(
                "Updating the state failed, will retry with login: %s(%s)" % (type(ex), ex)
            )
            await self.controller.login()
