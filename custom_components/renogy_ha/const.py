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

# Device info
ATTR_MANUFACTURER = "Renogy"
ATTR_MODEL = "Rover"
