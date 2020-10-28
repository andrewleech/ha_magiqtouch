"""The Seeley MagiQtouch integration."""
import asyncio

import voluptuous as vol

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .magiqtouch import MagiQtouch_Driver
from .const import DOMAIN
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.exceptions import ConfigEntryNotReady

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

# List the platforms that you want to support.
PLATFORMS = [CLIMATE_DOMAIN]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Seeley MagiQtouch component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Seeley MagiQtouch from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    driver = MagiQtouch_Driver(user=username, password=password)

    try:
        success = await driver.login()
        if not success:
            raise ConfigEntryNotReady
    except Exception as exception:
        raise ConfigEntryNotReady from exception

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = driver

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


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
        driver = hass.data[DOMAIN].pop(entry.entry_id)
        driver.logout()

    return unload_ok
