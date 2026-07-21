"""Constants for the Seeley MagIQtouch integration."""

import math
from datetime import timedelta
from collections import namedtuple
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    UnitOfTemperature,
)

DOMAIN = "magiqtouch"

# DataUpdateCoordinator polling rate
SCAN_INTERVAL = timedelta(seconds=60)

FAN_MIN = "min"
FAN_MAX = "max"


class CONF:
    USERNAME = CONF_USERNAME
    PASSWORD = CONF_PASSWORD
    VERBOSE = "log_json"
    TITLE = "title"
    STATE = "state"
    SYS_STATE = "system_state"
    ZONES = "zone_list"


MODE_COOLER = "COOL"
MODE_COOLER_FAN = "COOLER_FAN"
# MODE_COOLER_AOC = "COOLER_AOC"  # todo: don't know if this exists
MODE_HEATER = "HEAT"
MODE_HEATER_FAN = "HEATER_FAN"

CONTROL_MODE_FAN = "FAN"
CONTROL_MODE_TEMP = "TEMP"  # todo check

ZoneType = namedtuple("ZoneType", ("type", "name"))

ZONE_TYPE_NONE = "NONE"
ZONE_TYPE_COMMON = "COMMON"

ZONE_NONE = ZoneType(ZONE_TYPE_NONE, None)
ZONE_COMMON = ZoneType(ZONE_TYPE_COMMON, None)


def is_valid_temperature(value, unit) -> bool:
    """Return whether a controller temperature is plausible rather than a sentinel."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    if unit == UnitOfTemperature.FAHRENHEIT:
        return -58 <= value < 212
    return -50 <= value < 100
