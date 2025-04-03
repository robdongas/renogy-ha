"""Constants for the Renogy BLE integration."""

import logging

DOMAIN = "renogy"

LOGGER = logging.getLogger(__name__)

# BLE scanning constants
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 10  # seconds
MAX_SCAN_INTERVAL = 600  # seconds

# Renogy BT-1 and BT-2 module identifiers - devices advertise with these prefixes
RENOGY_BT_PREFIX = "BT-TH-"

# Configuration parameters
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DEVICE_TYPE = "device_type"  # New constant for device type

# Device info
ATTR_MANUFACTURER = "Renogy"
ATTR_MODEL = "Rover"

# List of supported device types
DEVICE_TYPES = ["controller", "battery", "inverter"]
DEFAULT_DEVICE_TYPE = "controller"

# List of fully supported device types (currently only controller)
SUPPORTED_DEVICE_TYPES = ["controller"]

# BLE Characteristics and Service UUIDs
RENOGY_READ_CHAR_UUID = (
    "0000fff1-0000-1000-8000-00805f9b34fb"  # Characteristic for reading data
)
RENOGY_WRITE_CHAR_UUID = (
    "0000ffd1-0000-1000-8000-00805f9b34fb"  # Characteristic for writing commands
)

# Time in minutes to wait before attempting to reconnect to unavailable devices
UNAVAILABLE_RETRY_INTERVAL = 10

# Maximum time to wait for a notification response (seconds)
MAX_NOTIFICATION_WAIT_TIME = 2.0

# Default device ID for Renogy devices
DEFAULT_DEVICE_ID = 0xFF

# Modbus commands for requesting data
COMMANDS = {
    "controller": {
        "device_info": (3, 12, 8),
        "device_id": (3, 26, 1),
        "battery": (3, 57348, 1),
        "pv": (3, 256, 34),
    },
}
