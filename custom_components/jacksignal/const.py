"""Shared configuration keys and priorities."""

from enum import IntEnum

DOMAIN = "jacksignal"
PLATFORMS = ["media_player"]
LOCAL_PREFIX = "media-source://media_source/"
ALARM = "alarm"
RULES = "rules"
SENSOR_RULES = "sensor_rules"

EVENTS = ("triggered", "pending", "arming", "armed", "disarmed", "failed_to_arm")


class Priority(IntEnum):
    """Priority shared by manual playback, automations and Alarmo."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


DEFAULT_PRIORITIES = {
    "triggered": Priority.CRITICAL,
    "pending": Priority.HIGH,
    "arming": Priority.NORMAL,
    "armed": Priority.NORMAL,
    "disarmed": Priority.HIGH,
    "failed_to_arm": Priority.HIGH,
}
