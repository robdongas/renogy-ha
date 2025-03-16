"""BLE communication module for Renogy devices."""

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from .const import (
    DEFAULT_SCAN_INTERVAL,
    LOGGER,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    RENOGY_BT_PREFIX,
)

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


def modbus_crc(data: bytes) -> tuple:
    """Calculate the Modbus CRC16 of the given data.

    Returns a tuple (crc_low, crc_high) where the low byte is sent first.
    """
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return (crc & 0xFF, (crc >> 8) & 0xFF)


def create_modbus_read_request(
    device_id: int, function_code: int, register: int, word_count: int
) -> bytearray:
    """Build a Modbus read request frame.

    The frame consists of:
      [device_id, function_code, register_high, register_low, word_count_high, word_count_low, crc_high, crc_low]

    Note: Many Modbus implementations send the CRC as low byte first; adjust if needed.
    """
    frame = bytearray(
        [
            device_id,
            function_code,
            (register >> 8) & 0xFF,
            register & 0xFF,
            (word_count >> 8) & 0xFF,
            word_count & 0xFF,
        ]
    )
    crc_low, crc_high = modbus_crc(frame)
    frame.extend([crc_low, crc_high])
    LOGGER.debug("create_request_payload: %s (%s)", register, list(frame))
    LOGGER.debug("Testing restart")
    return frame


# TODO: Make this configurable or automatically discover
default_device_id = 0xFF

# Modbus commands for requesting data
device_info_cmd = create_modbus_read_request(default_device_id, 3, 12, 8)
device_id_cmd = create_modbus_read_request(default_device_id, 3, 26, 1)
battery_cmd = create_modbus_read_request(default_device_id, 3, 57348, 1)
pv_cmd = create_modbus_read_request(default_device_id, 3, 256, 34)


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
            if self.failure_count > 0:
                LOGGER.info(
                    "Device %s communication restored after %s consecutive failures",
                    self.name,
                    self.failure_count,
                )
            self.failure_count = 0
            if not self.available:
                LOGGER.info("Device %s is now available", self.name)
                self.available = True
        else:
            self.failure_count += 1
            LOGGER.warning(
                "Communication failure with device %s (failure %s of %s)",
                self.name,
                self.failure_count,
                self.max_failures,
            )

            if self.failure_count >= self.max_failures and self.available:
                LOGGER.warning(
                    "Device %s marked unavailable after %s consecutive failures",
                    self.name,
                    self.max_failures,
                )
                self.available = False

    def update_parsed_data(self, raw_data: bytes) -> bool:
        """Parse the raw data using the renogy-ble library."""
        if not raw_data:
            LOGGER.error("No data received from device %s.", self.name)
            return False
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
        LOGGER.debug("Attempting to read data from device: %s", device.name)

        if not device.is_available:
            LOGGER.warning(
                "Device %s is marked as unavailable, skipping data read", device.name
            )
            return False

        success = False
        client = BleakClient(device.ble_device)

        try:
            await client.connect()
            if client.is_connected:
                LOGGER.debug("Connected to device %s", device.name)

                # Subscribe to notifications by defining a handler
                notification_data = bytearray()

                def notification_handler(sender, data):
                    notification_data.extend(data)

                await client.start_notify(RENOGY_READ_CHAR_UUID, notification_handler)

                # Build and send the command for device info
                await client.write_gatt_char(RENOGY_WRITE_CHAR_UUID, device_info_cmd)
                await asyncio.sleep(2)  # wait longer for notification data
                device_info_data = bytes(notification_data)
                LOGGER.debug("Received device_data length: %d", len(device_info_data))
                notification_data.clear()

                # Build and send the command for device id
                await client.write_gatt_char(RENOGY_WRITE_CHAR_UUID, device_id_cmd)
                await asyncio.sleep(2)  # wait longer for notification data
                device_id_data = bytes(notification_data)
                LOGGER.debug("Received device_data length: %d", len(device_id_data))
                notification_data.clear()

                # Build and send the Modbus read command for battery info
                await client.write_gatt_char(RENOGY_WRITE_CHAR_UUID, battery_cmd)
                await asyncio.sleep(2)  # wait longer for notification data
                battery_data = bytes(notification_data)
                LOGGER.debug("Received battery_data length: %d", len(battery_data))
                notification_data.clear()

                # Build and send the command for PV info
                await client.write_gatt_char(RENOGY_WRITE_CHAR_UUID, pv_cmd)
                await asyncio.sleep(2)  # wait longer for notification data
                pv_data = bytes(notification_data)
                LOGGER.debug("Received pv_data length: %d", len(pv_data))
                notification_data.clear()

                await client.stop_notify(RENOGY_READ_CHAR_UUID)

                # Combine the received data
                combined_data = (
                    device_info_data + device_id_data + battery_data + pv_data
                )

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
            if client.is_connected:
                await client.disconnect()
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
