"""Config flow for Seeley MagIQtouch integration."""
import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.core import callback

from .magiqtouch import MagIQtouch_Driver
from .const import DOMAIN, CONF  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__name__)


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF.USERNAME): str,
        vol.Required(CONF.PASSWORD): str,
    }
)


async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # If your PyPI package is not built with async, pass your methods
    # to the executor:
    # await hass.async_add_executor_job(
    #     your_validate_func, data[CONF.USERNAME], data[CONF.PASSWORD]
    # )

    driver = MagIQtouch_Driver(user=data[CONF.USERNAME], password=data[CONF.PASSWORD])

    try:
        if not await driver.login():
            raise InvalidAuth
    except Exception as e:
        import traceback

        trace_text = traceback.format_exc()
        _LOGGER.error(f"Could not connect: {str(e)} {trace_text}")
        if "InvalidSignatureException" in trace_text:
            raise InvalidTime
        raise CannotConnect

    # Return info that you want to store in the config entry.
    await driver.startup()
    return driver.update_config_data(data)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for Seeley MagIQtouch."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

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
            return self.async_create_entry(title=info["title"], data=info)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    # def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
    #    """Initialize options flow."""
    #    self.entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Dict[str, Any]:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="Settings", options=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF.VERBOSE,
                        default=self.config_entry.options.get(CONF.VERBOSE),
                    ): bool
                }
            ),
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""


class InvalidTime(exceptions.HomeAssistantError):
    """Error to indicate auth failed due to incorrect system time."""
