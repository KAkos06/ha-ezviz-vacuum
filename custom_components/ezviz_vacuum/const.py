"""Constants for the EZVIZ Vacuum integration."""

from datetime import timedelta

DOMAIN = "ezviz_vacuum"
PLATFORMS = ["vacuum", "sensor", "binary_sensor"]

CONF_REGION = "region"
DEFAULT_REGION = "eu"

DEFAULT_POLL_INTERVAL = timedelta(minutes=5)
MQTT_DISCONNECTED_POLL_INTERVAL = timedelta(seconds=60)
MQTT_REFRESH_DEBOUNCE_SECONDS = 2
MQTT_RECONNECT_INITIAL_SECONDS = 5
MQTT_RECONNECT_MAX_SECONDS = 300

SUPPORTED_CATEGORY = "SweepingRobot"
