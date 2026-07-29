"""Constants for the EZVIZ Vacuum integration."""

from datetime import timedelta

DOMAIN = "ezviz_vacuum"
PLATFORMS = ["vacuum", "sensor", "binary_sensor", "select", "switch"]

CONF_REGION = "region"
DEFAULT_REGION = "eu"

DEFAULT_POLL_INTERVAL = timedelta(seconds=15)

SUPPORTED_CATEGORY = "SweepingRobot"
