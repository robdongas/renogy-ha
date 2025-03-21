"""BLE communication module for Renogy devices."""

import asyncio
from datetime import datetime, timedelta
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

# Time in minutes to wait before attempting to reconnect to unavailable devices
UNAVAILABLE_RETRY_INTERVAL = 10

# Maximum time to wait for a notification response (seconds)
MAX_NOTIFICATION_WAIT_TIME = 2.0


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
    LOGGER.debug(f"create_request_payload: {register} ({list(frame)})")
    return frame


# TODO: Make this configurable or automatically discover
default_device_id = 0xFF

# Modbus commands for requesting data
commands = {
    "device_info": (3, 12, 8),
    "device_id": (3, 26, 1),
    "battery": (3, 57348, 1),
    "pv": (3, 256, 34),
}


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
        # Track when device was last marked as unavailable
        self.last_unavailable_time: Optional[datetime] = None

    @property
    def is_available(self) -> bool:
        """Return True if device is available."""
        return self.available and self.failure_count < self.max_failures

    @property
    def should_retry_connection(self) -> bool:
        """Check if we should retry connecting to an unavailable device."""
        if self.is_available:
            return True

        # If we've never set an unavailable time, set it now
        if self.last_unavailable_time is None:
            self.last_unavailable_time = datetime.now()
            return False

        # Check if enough time has passed to retry
        retry_time = self.last_unavailable_time + timedelta(
            minutes=UNAVAILABLE_RETRY_INTERVAL
        )
        if datetime.now() >= retry_time:
            LOGGER.info(
                f"Retry interval reached for unavailable device {self.name}. Attempting reconnection..."
            )
            # Reset the unavailable time for the next retry interval
            self.last_unavailable_time = datetime.now()
            return True

        return False

    def update_availability(self, success: bool) -> None:
        """Update the availability based on success/failure of communication."""
        if success:
            if self.failure_count > 0:
                LOGGER.info(
                    f"Device {self.name} communication restored after {self.failure_count} consecutive failures"
                )
            self.failure_count = 0
            if not self.available:
                LOGGER.info(f"Device {self.name} is now available")
                self.available = True
                self.last_unavailable_time = None
        else:
            self.failure_count += 1
            LOGGER.warning(
                f"Communication failure with device {self.name} (failure {self.failure_count} of {self.max_failures})"
            )

            if self.failure_count >= self.max_failures and self.available:
                LOGGER.warning(
                    f"Device {self.name} marked unavailable after {self.max_failures} consecutive failures"
                )
                self.available = False
                self.last_unavailable_time = datetime.now()

    def update_parsed_data(self, raw_data: bytes, register: int) -> bool:
        """Parse the raw data using the renogy-ble library."""
        if not raw_data:
            LOGGER.error(f"No data received from device {self.name}.")
            return False
        if not RenogyParser:
            LOGGER.error("RenogyParser library not available. Unable to parse data.")
            return False

        try:
            # Parse the raw data using the renogy-ble library
            parsed = RenogyParser.parse(
                raw_data, self.model, register
            )  # Placeholder for register

            if not parsed:
                LOGGER.warning(f"No data parsed from raw data for device {self.name}")
                return False

            # Update the stored parsed data
            self.parsed_data.update(parsed)
            LOGGER.debug(
                f"Successfully parsed data for device {self.name}: {self.parsed_data}"
            )
            return True
        except Exception as e:
            LOGGER.error(f"Error parsing data for device {self.name}: {str(e)}")
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
                        f"Found Renogy device: {device.name} ({device.address})"
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

            LOGGER.debug(f"Found {len(renogy_devices)} Renogy devices")
            return renogy_devices
        except Exception as e:
            LOGGER.error(f"Error scanning for Renogy devices: {str(e)}")
            return []

    async def read_device_data(self, device: RenogyBLEDevice) -> bool:
        """Read data from a Renogy BLE device."""
        LOGGER.debug(f"Attempting to read data from device: {device.name}")

        # Check if the device is unavailable and we should attempt reconnection
        if not device.is_available and not device.should_retry_connection:
            LOGGER.debug(
                f"Device {device.name} is unavailable and not yet due for retry attempt"
            )
            return False

        success = False
        client = BleakClient(device.ble_device)

        try:
            await client.connect()
            if client.is_connected:
                LOGGER.debug(f"Connected to device {device.name}")

                # Create an event that will be set when notification data is received
                notification_event = asyncio.Event()
                notification_data = bytearray()

                def notification_handler(sender, data):
                    notification_data.extend(data)
                    # Set the event to indicate data has been received
                    notification_event.set()

                await client.start_notify(RENOGY_READ_CHAR_UUID, notification_handler)

                # Loop through each command and parse them separately
                for cmd_name, cmd in commands.items():
                    # Clear the notification data and event before sending new command
                    notification_data.clear()
                    notification_event.clear()

                    # Send the command
                    modbus_request = create_modbus_read_request(default_device_id, *cmd)
                    LOGGER.debug(f"{cmd_name} command: {list(modbus_request)}")
                    await client.write_gatt_char(RENOGY_WRITE_CHAR_UUID, modbus_request)

                    # Wait for notification data with timeout
                    try:
                        await asyncio.wait_for(
                            notification_event.wait(), MAX_NOTIFICATION_WAIT_TIME
                        )
                    except asyncio.TimeoutError:
                        LOGGER.warning(
                            f"Timeout waiting for {cmd_name} data from device {device.name}"
                        )
                        continue

                    # Process the received data
                    result_data = bytes(notification_data)
                    LOGGER.debug(f"Received {cmd_name} data length: {len(result_data)}")
                    LOGGER.debug(f"{cmd_name} data (register {cmd[1]}): {result_data}")

                    if device.update_parsed_data(result_data, register=cmd[1]):
                        LOGGER.info(
                            f"Successfully read and parsed {cmd_name} data from device {device.name}"
                        )
                        success = True
                    else:
                        LOGGER.warning(
                            f"Failed to parse data from device {device.name}"
                        )

                await client.stop_notify(RENOGY_READ_CHAR_UUID)

            else:
                LOGGER.warning(f"Failed to connect to device {device.name}")

        except Exception as e:
            LOGGER.error(f"Error reading data from device {device.name}: {str(e)}")
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
            f"Starting Renogy BLE polling with interval {self.scan_interval} seconds"
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
                            LOGGER.error(f"Error in data callback: {str(e)}")

            except Exception as e:
                LOGGER.error(f"Error in polling loop: {str(e)}")

            # Wait for the next scan interval
            await asyncio.sleep(self.scan_interval)
