"""Constants for the EZVIZ Vacuum integration."""

from datetime import timedelta

DOMAIN = "ezviz_vacuum"
PLATFORMS = ["vacuum", "sensor", "binary_sensor", "select", "switch"]

CONF_REGION = "region"
DEFAULT_REGION = "eu"

DEFAULT_POLL_INTERVAL = timedelta(seconds=15)
ACTIVE_POLL_INTERVAL = timedelta(seconds=3)
COMMAND_TRANSITION_GRACE_SECONDS = 6
START_CONTROL_LOCK_SECONDS = 5

SUPPORTED_CATEGORY = "SweepingRobot"
