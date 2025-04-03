"""Mock implementations of Home Assistant bluetooth components for testing."""

from enum import Enum
from unittest.mock import MagicMock


class BluetoothScanningMode(str, Enum):
    """Scanning modes for the Bluetooth scanner."""

    ACTIVE = "active"
    PASSIVE = "passive"


class BluetoothChange(str, Enum):
    """Bluetooth change types."""

    ADVERTISEMENT = "advertisement"
    UNAVAILABLE = "unavailable"


class BluetoothServiceInfoBleak:
    """Mock BluetoothServiceInfoBleak for testing."""

    def __init__(self, address="00:00:00:00:00:00", name="TestDevice", rssi=-60):
        """Initialize the service info."""
        self.address = address
        self.name = name
        self.rssi = rssi
        self.device = MagicMock()
        self.device.address = address
        self.device.name = name
        self.device.rssi = rssi
        self.advertisement = MagicMock()
        self.advertisement.rssi = rssi


# Create a mock bluetooth module
bluetooth = MagicMock()
bluetooth.async_discovered_service_info = MagicMock()
bluetooth.async_ble_device_from_address = MagicMock()
bluetooth.async_register_callback = MagicMock()
bluetooth.async_last_service_info = MagicMock()

# Create the Home Assistant bluetooth components module structure
components = MagicMock()
components.bluetooth = bluetooth
components.bluetooth.BluetoothServiceInfoBleak = BluetoothServiceInfoBleak
components.bluetooth.BluetoothScanningMode = BluetoothScanningMode
components.bluetooth.BluetoothChange = BluetoothChange
components.bluetooth.active_update_coordinator = MagicMock()
components.bluetooth.active_update_coordinator.ActiveBluetoothDataUpdateCoordinator = (
    MagicMock()
)
