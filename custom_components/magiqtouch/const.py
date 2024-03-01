"""Constants for the Seeley MagiQtouch integration."""

from homeassistant.const import (  # noqa:F401
    ATTR_DEVICE_CLASS,
    ATTR_ICON,
    ATTR_UNIT_OF_MEASUREMENT,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
    DEVICE_CLASS_CO,
    DEVICE_CLASS_CO2,
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_PRESSURE,
    DEVICE_CLASS_TEMPERATURE,
    PERCENTAGE,
    PRESSURE_HPA,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)

DOMAIN = "magiqtouch"

FAN_MIN = "min"
FAN_MAX = "max"

CONF_VERBOSE = "log_json"

SENSOR = "sensor"
CLIMATE = "climate"
PLATFORMS = [CLIMATE, SENSOR]

API_CO = "co"
API_CO2 = "co2"
API_DUST = "dust"
API_HUMIDITY = "humidity"
API_NO2 = "no2"
API_OZONE = "ozone"
API_PRESSURE = "pressure"
API_TEMP = "temp"
API_VOC = "voc"

ATTR_LABEL = "label"
ATTR_UNIQUE_ID = "unique_id"


SENSOR_TYPES = {
    API_HUMIDITY: {
        ATTR_DEVICE_CLASS: DEVICE_CLASS_HUMIDITY,
        ATTR_ICON: "mdi:water-percent",
        ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE,
        ATTR_LABEL: "Humidity",
        ATTR_UNIQUE_ID: API_HUMIDITY,
    },
    API_TEMP: {
        ATTR_DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        ATTR_ICON: "mdi:thermometer",
        ATTR_UNIT_OF_MEASUREMENT: TEMP_FAHRENHEIT,
        ATTR_LABEL: "Temperature",
        ATTR_UNIQUE_ID: API_TEMP,
    },
}
