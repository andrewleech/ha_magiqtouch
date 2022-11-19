"""Config flow for Seeley MagiQtouch integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from .magiqtouch import MagiQtouch_Driver
from .const import DOMAIN  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__name__)

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): str, 
    vol.Required(CONF_PASSWORD): str,
})


async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # If your PyPI package is not built with async, pass your methods
    # to the executor:
    # await hass.async_add_executor_job(
    #     your_validate_func, data[CONF_USERNAME], data[CONF_PASSWORD]
    # )

    hub = MagiQtouch_Driver(user=data[CONF_USERNAME], password=data[CONF_PASSWORD])

    try:
        if not await hub.login():
            raise InvalidAuth
    except Exception as e:
        import traceback
        trace_text = traceback.format_exc()
        _LOGGER.error(f"Could not connect: {str(e)} {trace_text}"	)
        if "InvalidSignatureException" in trace_text:
            raise InvalidTime
        raise CannotConnect

    # Return info that you want to store in the config entry.
    return {"title": "MagiQtouch"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Seeley MagiQtouch."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except InvalidTime:
            _LOGGER.error("invalid_system_time")
            errors["base"] = "invalid_system_time"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""

class InvalidTime(exceptions.HomeAssistantError):
    """Error to indicate auth failed due to incorrect system time."""
