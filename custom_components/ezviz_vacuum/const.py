"""Constants for the EZVIZ Vacuum integration."""

from datetime import timedelta

DOMAIN = "ezviz_vacuum"
PLATFORMS = ["vacuum", "sensor", "binary_sensor", "select", "switch"]

CONF_REGION = "region"
DEFAULT_REGION = "eu"

DEFAULT_POLL_INTERVAL = timedelta(seconds=60)
MQTT_REFRESH_DEBOUNCE_SECONDS = 2
MQTT_UNROUTED_REFRESH_MIN_SECONDS = 30
MQTT_RECONNECT_INITIAL_SECONDS = 20
MQTT_RECONNECT_MAX_SECONDS = 300

SUPPORTED_CATEGORY = "SweepingRobot"
