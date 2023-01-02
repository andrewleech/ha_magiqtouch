"""Constants for the Seeley MagiQtouch integration."""
from datetime import timedelta

DOMAIN = "magiqtouch"

# DataUpdateCoordinator polling rate
SCAN_INTERVAL = timedelta(seconds=30)

FAN_MIN = "min"
FAN_MAX = "max"

CONF_VERBOSE = "log_json"

MODE_COOLER = "COOL"
MODE_COOLER_FAN = "COOLER_FAN"
MODE_COOLER_AOC = "COOLER_AOC"  # todo: don't know if this exists
MODE_HEATER = "HEAT"
MODE_HEATER_FAN = "HEATER_FAN"

CONTROL_MODE_FAN = "FAN"
CONTROL_MODE_TEMP = "TEMP"  # todo check
