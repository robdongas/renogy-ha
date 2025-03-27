"""BLE communication module for Renogy devices."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
)
from homeassistant.core import callback

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

    async def update(self) -> None:
        """Perform a simple connectivity check."""
        from bleak import BleakClient

        client = BleakClient(self.ble_device)
        try:
            await client.connect()
        finally:
            try:
                await client.disconnect()
            except EOFError:
                # Suppress EOFError from dbus_fast disconnect
                pass

    async def stop(self) -> None:
        """Placeholder stop method to satisfy the config flow."""
        pass

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

    def update_parsed_data(
        self, raw_data: bytes, register: int, cmd_name: str = "unknown"
    ) -> bool:
        """Parse the raw data using the renogy-ble library.

        Args:
            raw_data: The raw data received from the device
            register: The register address this data corresponds to
            cmd_name: The name of the command (for logging purposes)

        Returns:
            True if parsing was successful (even partially), False otherwise
        """
        if not raw_data:
            LOGGER.error(
                f"No data received from device {self.name} for command {cmd_name}."
            )
            return False

        if not RenogyParser:
            LOGGER.error("RenogyParser library not available. Unable to parse data.")
            return False

        try:
            # Check for minimum valid response length
            # Modbus response format: device_id(1) + function_code(1) + byte_count(1) + data(n) + crc(2)
            if (
                len(raw_data) < 5
            ):  # At minimum, we need these 5 bytes for a valid response
                LOGGER.warning(
                    f"Response too short for {cmd_name}: {len(raw_data)} bytes. Raw data: {raw_data.hex()}"
                )
                return False

            # Basic validation of Modbus response
            function_code = raw_data[1] if len(raw_data) > 1 else 0
            if function_code & 0x80:  # Error response
                error_code = raw_data[2] if len(raw_data) > 2 else 0
                LOGGER.error(
                    f"Modbus error in {cmd_name} response: function code {function_code}, error code {error_code}"
                )
                return False

            # Parse the raw data using the renogy-ble library
            # The parser will handle partial data and log appropriate warnings
            parsed = RenogyParser.parse(raw_data, self.model, register)

            if not parsed:
                LOGGER.warning(
                    f"No data parsed from {cmd_name} response (register {register}). Length: {len(raw_data)}"
                )
                return False

            # Update the stored parsed data with whatever we could get
            self.parsed_data.update(parsed)

            # Log the successful parsing
            LOGGER.debug(
                f"Successfully parsed {cmd_name} data from device {self.name}: {parsed}"
            )
            return True

        except Exception as e:
            LOGGER.error(
                f"Error parsing {cmd_name} data from device {self.name}: {str(e)}"
            )
            # Log additional debug info to help diagnose the issue
            LOGGER.debug(
                f"Raw data for {cmd_name} (register {register}): {raw_data.hex() if raw_data else 'None'}, Length: {len(raw_data) if raw_data else 0}"
            )
            return False


class RenogyBLEClient:
    """Client to handle BLE communication with Renogy devices."""

    def __init__(
        self,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        data_callback: Optional[Callable[[RenogyBLEDevice], None]] = None,
        hass=None,
        device_address: Optional[str] = None,
    ):
        """Initialize the BLE client."""
        self.discovered_devices: Dict[str, RenogyBLEDevice] = {}
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self.scan_interval = max(
            MIN_SCAN_INTERVAL, min(scan_interval, MAX_SCAN_INTERVAL)
        )
        self.data_callback = data_callback
        self.hass = hass
        self._unload_callbacks: List[Callable] = []
        self._discovered_addresses: Set[str] = set()
        self.device_address = device_address  # Track specific device address

    def is_renogy_device(self, device: BLEDevice) -> bool:
        """Check if a BLE device is a Renogy device by examining its name."""
        if device.name is None:
            return False
        return device.name.startswith(RENOGY_BT_PREFIX)

    async def scan_for_devices(self) -> List[RenogyBLEDevice]:
        """Scan for Renogy BLE devices using Home Assistant Bluetooth integration."""
        LOGGER.debug("Searching for Renogy devices via HA Bluetooth integration")

        renogy_devices = []

        # Get all discovered devices from Home Assistant
        if self.hass:
            service_infos = bluetooth.async_discovered_service_info(self.hass)

            for service_info in service_infos:
                # Skip devices that don't match our criteria
                if not service_info.name or not service_info.name.startswith(
                    RENOGY_BT_PREFIX
                ):
                    continue

                # If we have a specific device address, only process that one
                if self.device_address and service_info.address != self.device_address:
                    continue

                LOGGER.debug(
                    f"Found Renogy device: {service_info.name} ({service_info.address})"
                )

                # Either get existing device or create new one
                if service_info.address in self.discovered_devices:
                    renogy_device = self.discovered_devices[service_info.address]
                    # Get an updated BLEDevice from HA
                    ble_device = bluetooth.async_ble_device_from_address(
                        self.hass, service_info.address, connectable=True
                    )
                    if ble_device:
                        renogy_device.ble_device = ble_device
                        renogy_device.rssi = ble_device.rssi
                        renogy_device.last_seen = datetime.now()
                else:
                    # Get a BLEDevice from HA
                    ble_device = bluetooth.async_ble_device_from_address(
                        self.hass, service_info.address, connectable=True
                    )
                    if ble_device:
                        renogy_device = RenogyBLEDevice(ble_device)
                        self.discovered_devices[service_info.address] = renogy_device

                        # Register for unavailable notifications
                        if service_info.address not in self._discovered_addresses:
                            self._register_unavailable_tracking(service_info.address)
                            self._discovered_addresses.add(service_info.address)

                if service_info.address in self.discovered_devices:
                    renogy_devices.append(self.discovered_devices[service_info.address])

            LOGGER.debug(f"Found {len(renogy_devices)} matching Renogy devices")
        else:
            LOGGER.error("Home Assistant instance not available for Bluetooth scanning")

        return renogy_devices

    async def get_device_by_address(self, address: str) -> Optional[RenogyBLEDevice]:
        """Get a specific device by address."""
        if address in self.discovered_devices:
            return self.discovered_devices[address]

        # Try to find the device
        if self.hass:
            service_info = bluetooth.async_last_service_info(self.hass, address)
            if (
                service_info
                and service_info.name
                and service_info.name.startswith(RENOGY_BT_PREFIX)
            ):
                ble_device = bluetooth.async_ble_device_from_address(
                    self.hass, address, connectable=True
                )
                if ble_device:
                    renogy_device = RenogyBLEDevice(ble_device)
                    self.discovered_devices[address] = renogy_device

                    # Register for unavailable tracking
                    if address not in self._discovered_addresses:
                        self._register_unavailable_tracking(address)
                        self._discovered_addresses.add(address)

                    return renogy_device

        return None

    def _register_unavailable_tracking(self, address: str) -> None:
        """Register for unavailable notifications from Home Assistant."""
        # Skip if we only care about a specific device that's not this one
        if self.device_address and address != self.device_address:
            return

        if not self.hass:
            return

        def _unavailable_callback(
            service_info: bluetooth.BluetoothServiceInfoBleak,
        ) -> None:
            """Handle device becoming unavailable."""
            LOGGER.debug(f"Device {address} is no longer seen by HA Bluetooth")
            if address in self.discovered_devices:
                device = self.discovered_devices[address]
                device.update_availability(False)

        cancel = bluetooth.async_track_unavailable(
            self.hass, _unavailable_callback, address, connectable=True
        )
        self._unload_callbacks.append(cancel)

    async def register_bluetooth_callbacks(self) -> None:
        """Register callbacks for Bluetooth discovery."""
        if not self.hass:
            LOGGER.error(
                "Cannot register Bluetooth callbacks without Home Assistant instance"
            )
            return

        @callback
        def _async_discovered_device(
            service_info: bluetooth.BluetoothServiceInfoBleak,
            change: bluetooth.BluetoothChange,
        ) -> None:
            """Handle a discovered Bluetooth device."""
            # If we only care about a specific device, ignore others
            if self.device_address and service_info.address != self.device_address:
                return

            if (
                service_info.name
                and service_info.name.startswith(RENOGY_BT_PREFIX)
                and service_info.address not in self._discovered_addresses
            ):
                LOGGER.info(
                    f"Discovered new Renogy device: {service_info.name} ({service_info.address})"
                )

                # Get a proper BLEDevice
                ble_device = bluetooth.async_ble_device_from_address(
                    self.hass, service_info.address, connectable=True
                )

                if ble_device:
                    renogy_device = RenogyBLEDevice(ble_device)
                    self.discovered_devices[service_info.address] = renogy_device
                    self._discovered_addresses.add(service_info.address)

                    # Register for unavailable tracking
                    self._register_unavailable_tracking(service_info.address)

                    # Process this device immediately instead of waiting for next scan
                    asyncio.create_task(self._process_device(renogy_device))

        # Register for Bluetooth discovery callbacks with filter for our specific device if needed
        matcher = {"local_name": f"{RENOGY_BT_PREFIX}*"}
        if self.device_address:
            matcher = {"address": self.device_address}

        unload_callback = bluetooth.async_register_callback(
            self.hass,
            _async_discovered_device,
            matcher,
            BluetoothScanningMode.ACTIVE,
        )

        self._unload_callbacks.append(unload_callback)
        LOGGER.debug(
            f"Registered for Renogy device discovery callbacks with matcher: {matcher}"
        )

    async def read_device_data(self, device: RenogyBLEDevice) -> bool:
        """Read data from a Renogy BLE device."""
        LOGGER.debug(f"Attempting to read data from device: {device.name}")

        # Check if the device is unavailable and we should attempt reconnection
        if not device.is_available and not device.should_retry_connection:
            LOGGER.debug(
                f"Device {device.name} is unavailable and not yet due for retry attempt"
            )
            return False

        # Update the BLEDevice if needed
        if self.hass:
            updated_ble_device = bluetooth.async_ble_device_from_address(
                self.hass, device.address, connectable=True
            )
            if updated_ble_device:
                device.ble_device = updated_ble_device
                device.rssi = updated_ble_device.rssi

        success = False
        client = BleakClient(device.ble_device)
        any_command_succeeded = False

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
                    LOGGER.debug(
                        f"{cmd_name} data (register {cmd[1]}): {result_data.hex()}"
                    )

                    # Try to parse this command's data
                    cmd_success = device.update_parsed_data(
                        result_data, register=cmd[1], cmd_name=cmd_name
                    )

                    if cmd_success:
                        LOGGER.info(
                            f"Successfully read and parsed {cmd_name} data from device {device.name}"
                        )
                        any_command_succeeded = True
                    else:
                        LOGGER.warning(
                            f"Failed to parse {cmd_name} data from device {device.name}"
                        )

                await client.stop_notify(RENOGY_READ_CHAR_UUID)

                # Consider the overall operation successful if at least one command was parsed
                success = any_command_succeeded

            else:
                LOGGER.warning(f"Failed to connect to device {device.name}")

        except Exception as e:
            LOGGER.error(f"Error reading data from device {device.name}: {str(e)}")
        finally:
            if client and client.is_connected:
                try:
                    await client.disconnect()
                except Exception as e:
                    LOGGER.warning(
                        f"Error disconnecting from device {device.name}: {str(e)}"
                    )

            # Update device availability, but count it as a success if any command worked
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

        # Register for Bluetooth discovery callbacks
        if self.hass:
            await self.register_bluetooth_callbacks()

        # Start polling task
        self._scan_task = asyncio.create_task(self._polling_loop())

    async def stop_polling(self) -> None:
        """Stop the BLE polling loop."""
        if not self._running:
            return

        LOGGER.info("Stopping Renogy BLE polling")
        self._running = False

        # Cancel all bluetooth callbacks
        for callback in self._unload_callbacks:
            callback()
        self._unload_callbacks.clear()

        # Cancel the polling task
        if self._scan_task is not None:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

    async def _process_device(self, device: RenogyBLEDevice) -> None:
        """Process a single device, reading its data."""
        success = await self.read_device_data(device)

        # If read was successful and we have a callback, call it
        if success and self.data_callback and device.parsed_data:
            try:
                self.data_callback(device)
            except Exception as e:
                LOGGER.error(f"Error in data callback: {str(e)}")

    async def _polling_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                if self.device_address:
                    # Only get the specific device we're tracking
                    device = await self.get_device_by_address(self.device_address)
                    if device:
                        await self._process_device(device)
                else:
                    # Process all discovered devices
                    devices = await self.scan_for_devices()
                    for device in devices:
                        await self._process_device(device)

            except Exception as e:
                LOGGER.error(f"Error in polling loop: {str(e)}")

            # Wait for the next scan interval
            await asyncio.sleep(self.scan_interval)
