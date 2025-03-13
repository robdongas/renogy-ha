"""BLE communication module for Renogy devices."""

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .const import (
    DEFAULT_SCAN_INTERVAL,
    LOGGER,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    RENOGY_BT_PREFIX,
)

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

try:
    from renogy_ble import RenogyParser
except ImportError:
    LOGGER.error(
        "renogy-ble library not found! Please install it via pip install renogy-ble"
    )
    RenogyParser = None

# BLE Characteristics and Service UUIDs
RENOGY_READ_CHAR_UUID = (
    "0000fff1-0000-1000-8000-00805f9b34fb"  # Characteristic for reading data
)
RENOGY_WRITE_CHAR_UUID = (
    "0000ffd1-0000-1000-8000-00805f9b34fb"  # Characteristic for writing commands
)

# Modbus commands for requesting data
# Command structure: [Function code, Register start address (2 bytes), Number of registers (2 bytes)]
BATTERY_INFO_CMD = bytearray([0x03, 0x01, 0x00, 0x00, 0x08])
PV_INFO_CMD = bytearray([0x03, 0x01, 0x10, 0x00, 0x08])
DEVICE_INFO_CMD = bytearray([0x03, 0x00, 0x0C, 0x00, 0x08])


class RenogyBLEDevice:
    """Representation of a Renogy BLE device."""

    def __init__(self, ble_device: BLEDevice):
        """Initialize the Renogy BLE device."""
        self.ble_device = ble_device
        self.address = ble_device.address
        self.name = ble_device.name or "Unknown Renogy Device"
        self.rssi = ble_device.rssi
        self.last_seen = datetime.now()
        # To store last received data
        self.data: Optional[Dict[str, Any]] = None
        # Track consecutive failures
        self.failure_count = 0
        # Maximum allowed failures before marking device unavailable
        self.max_failures = 3
        # Device availability tracking
        self.available = True
        # Parsed data from device
        self.parsed_data: Dict[str, Any] = {}
        # Model type - default to rover
        self.model = "rover"

    @property
    def is_available(self) -> bool:
        """Return True if device is available."""
        return self.available and self.failure_count < self.max_failures

    def update_availability(self, success: bool) -> None:
        """Update the availability based on success/failure of communication."""
        if success:
            self.failure_count = 0
            if not self.available:
                LOGGER.info("Device %s is now available", self.name)
                self.available = True
        else:
            self.failure_count += 1
            if self.failure_count >= self.max_failures and self.available:
                LOGGER.warning(
                    "Device %s marked unavailable after %s consecutive failures",
                    self.name,
                    self.max_failures,
                )
                self.available = False

    def update_parsed_data(self, raw_data: bytes) -> bool:
        """Parse the raw data using the renogy-ble library."""
        if not RenogyParser:
            LOGGER.error("RenogyParser library not available. Unable to parse data.")
            return False

        try:
            # Parse the raw data using the renogy-ble library
            parsed = RenogyParser.parse(raw_data, self.model)

            if not parsed:
                LOGGER.warning("No data parsed from raw data for device %s", self.name)
                return False

            # Update the stored parsed data
            self.parsed_data.update(parsed)
            LOGGER.debug(
                "Successfully parsed data for device %s: %s",
                self.name,
                self.parsed_data,
            )
            return True
        except Exception as e:
            LOGGER.error("Error parsing data for device %s: %s", self.name, str(e))
            return False


class RenogyBLEClient:
    """Client to handle BLE communication with Renogy devices."""

    def __init__(
        self,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        data_callback: Optional[Callable[[RenogyBLEDevice], None]] = None,
    ):
        """Initialize the BLE client."""
        self.discovered_devices: Dict[str, RenogyBLEDevice] = {}
        self._scanner = BleakScanner()
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self.scan_interval = max(
            MIN_SCAN_INTERVAL, min(scan_interval, MAX_SCAN_INTERVAL)
        )
        self.data_callback = data_callback

    def is_renogy_device(self, device: BLEDevice) -> bool:
        """Check if a BLE device is a Renogy device by examining its name."""
        if device.name is None:
            return False
        return device.name.startswith(RENOGY_BT_PREFIX)

    async def scan_for_devices(self) -> List[RenogyBLEDevice]:
        """Scan for Renogy BLE devices and return a list of discovered devices."""
        LOGGER.debug("Starting BLE scan for Renogy devices")

        try:
            devices = await self._scanner.discover()
            renogy_devices = []

            for device in devices:
                if self.is_renogy_device(device):
                    LOGGER.debug(
                        "Found Renogy device: %s (%s)", device.name, device.address
                    )

                    # Either get existing device or create new one
                    if device.address in self.discovered_devices:
                        renogy_device = self.discovered_devices[device.address]
                        renogy_device.ble_device = (
                            device  # Update with latest device info
                        )
                        renogy_device.rssi = device.rssi
                        renogy_device.last_seen = datetime.now()
                    else:
                        renogy_device = RenogyBLEDevice(device)
                        self.discovered_devices[device.address] = renogy_device

                    renogy_devices.append(renogy_device)

            LOGGER.debug("Found %s Renogy devices", len(renogy_devices))
            return renogy_devices
        except Exception as e:
            LOGGER.error("Error scanning for Renogy devices: %s", str(e))
            return []

    async def read_device_data(self, device: RenogyBLEDevice) -> bool:
        """Read data from a Renogy BLE device."""
        LOGGER.debug("Attempting to read data from device: %s", device.name)

        if not device.is_available:
            LOGGER.warning(
                "Device %s is marked as unavailable, skipping data read", device.name
            )
            return False

        success = False
        client = BleakClient(device.ble_device)

        try:
            # Connect to the device
            await client.connect()
            if client.is_connected:
                LOGGER.debug("Connected to device %s", device.name)

                # Send commands and read responses
                # Battery info
                await client.write_gatt_char(RENOGY_WRITE_CHAR_UUID, BATTERY_INFO_CMD)
                battery_data = await client.read_gatt_char(RENOGY_READ_CHAR_UUID)

                # PV info
                await client.write_gatt_char(RENOGY_WRITE_CHAR_UUID, PV_INFO_CMD)
                pv_data = await client.read_gatt_char(RENOGY_READ_CHAR_UUID)

                # Device info
                await client.write_gatt_char(RENOGY_WRITE_CHAR_UUID, DEVICE_INFO_CMD)
                device_data = await client.read_gatt_char(RENOGY_READ_CHAR_UUID)

                # Combine the data (simple concatenation for now)
                combined_data = battery_data + pv_data + device_data

                # Parse the combined data
                if device.update_parsed_data(combined_data):
                    LOGGER.info(
                        "Successfully read and parsed data from device %s", device.name
                    )
                    success = True
                else:
                    LOGGER.warning("Failed to parse data from device %s", device.name)
            else:
                LOGGER.warning("Failed to connect to device %s", device.name)

        except Exception as e:
            LOGGER.error("Error reading data from device %s: %s", device.name, str(e))
        finally:
            # Ensure we disconnect even if there was an exception
            if client.is_connected:
                await client.disconnect()

            # Update device availability based on communication success
            device.update_availability(success)

            return success

    async def start_polling(self) -> None:
        """Start the BLE polling loop."""
        if self._running:
            LOGGER.warning("Polling already running, not starting again")
            return

        LOGGER.info(
            "Starting Renogy BLE polling with interval %s seconds", self.scan_interval
        )
        self._running = True
        self._scan_task = asyncio.create_task(self._polling_loop())

    async def stop_polling(self) -> None:
        """Stop the BLE polling loop."""
        if not self._running:
            return

        LOGGER.info("Stopping Renogy BLE polling")
        self._running = False
        if self._scan_task is not None:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

    async def _polling_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                devices = await self.scan_for_devices()

                # Process each discovered device
                for device in devices:
                    # Read data from the device
                    success = await self.read_device_data(device)

                    # If read was successful and we have a callback, call it
                    if success and self.data_callback and device.parsed_data:
                        try:
                            self.data_callback(device)
                        except Exception as e:
                            LOGGER.error("Error in data callback: %s", str(e))

            except Exception as e:
                LOGGER.error("Error in polling loop: %s", str(e))

            # Wait for the next scan interval
            await asyncio.sleep(self.scan_interval)
