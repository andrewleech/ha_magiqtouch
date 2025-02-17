"""Constants for the Seeley MagiQtouch integration."""
from datetime import timedelta

DOMAIN = "magiqtouch"

# DataUpdateCoordinator polling rate
SCAN_INTERVAL = timedelta(seconds=60)

FAN_MIN = "min"
FAN_MAX = "max"

CONF_VERBOSE = "log_json"

MODE_COOLER = "COOL"
MODE_COOLER_FAN = "COOLER_FAN"
# MODE_COOLER_AOC = "COOLER_AOC"  # todo: don't know if this exists
MODE_HEATER = "HEAT"
MODE_HEATER_FAN = "HEATER_FAN"

CONTROL_MODE_FAN = "FAN"
CONTROL_MODE_TEMP = "TEMP"  # todo check


class ZoneType:
    def __init__(self, label):
        self.label = label
        self._hash = hash("zt" + self.label)

    def __eq__(self, other):
        if isinstance(other, ZoneType):
            return other is self
        return other == self.label

    def __hash__(self):
        return self._hash


ZONE_TYPE_NONE = ZoneType("NONE")
ZONE_TYPE_COMMON = ZoneType("COMMON")
ZONE_TYPE_INDIVIDUAL = ZoneType("INDIVIDUAL")
ZONE_TYPE_SLAVE = ZoneType("SLAVE")
