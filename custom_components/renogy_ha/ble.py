"""BLE communication module for Renogy devices."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.core import CoreState, HomeAssistant, callback

from .const import (
    DEFAULT_SCAN_INTERVAL,
    LOGGER,
)

try:
    from renogy_ble import RenogyParser

    PARSER_AVAILABLE = True
except ImportError:
    LOGGER.error(
        "renogy-ble library not found! Please install it via pip install renogy-ble"
    )
    RenogyParser = None
    PARSER_AVAILABLE = False

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

        # Check if enough time has elapsed since the last poll
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

        if not PARSER_AVAILABLE:
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
            LOGGER.info(
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


class RenogyActiveBluetoothCoordinator(ActiveBluetoothDataUpdateCoordinator):
    """Class to manage fetching Renogy BLE data via active connections."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        address: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        device_data_callback: Optional[Callable[[RenogyBLEDevice], None]] = None,
    ):
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=logger,
            address=address,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_poll,
            mode=BluetoothScanningMode.ACTIVE,
            connectable=True,
        )
        self.device: Optional[RenogyBLEDevice] = None
        self.scan_interval = scan_interval
        self.last_poll_time: Optional[datetime] = None
        self.device_data_callback = device_data_callback
        self.logger.info(
            f"Initialized coordinator for {address} with {scan_interval}s interval"
        )

        # Add required properties for Home Assistant CoordinatorEntity compatibility
        self.last_update_success = True
        self._listeners = []
        self.update_interval = timedelta(seconds=scan_interval)
        self._unsub_refresh = None
        self._request_refresh_task = None

        # Add connection lock to prevent multiple concurrent connections
        self._connection_lock = asyncio.Lock()
        self._connection_in_progress = False

    async def async_request_refresh(self) -> None:
        """Request a refresh."""
        self.logger.debug("Manual refresh requested for device %s", self.address)

        # If a connection is already in progress, don't start another one
        if self._connection_in_progress:
            self.logger.debug(
                "Connection already in progress, skipping refresh request"
            )
            return

        # Get the last available service info for this device
        service_info = bluetooth.async_last_service_info(self.hass, self.address)
        if not service_info:
            self.logger.warning("No service info available for device %s", self.address)
            self.last_update_success = False
            return

        try:
            await self._async_poll(service_info)
            self.last_update_success = True
            # Notify listeners of the update
            for update_callback in self._listeners:
                update_callback()
        except Exception as err:
            self.last_update_success = False
            self.logger.error("Error refreshing device %s: %s", self.address, err)
            if self.device:
                self.device.update_availability(False)

    def async_add_listener(
        self, update_callback: Callable[[], None], context: Any = None
    ) -> Callable[[], None]:
        """Listen for data updates."""
        if update_callback not in self._listeners:
            self._listeners.append(update_callback)

        def remove_listener() -> None:
            """Remove update callback."""
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    def async_update_listeners(self) -> None:
        """Update all registered listeners."""
        for update_callback in self._listeners:
            update_callback()

    def _schedule_refresh(self) -> None:
        """Schedule a refresh with the update interval."""
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None

        # Schedule the next refresh based on our scan interval
        self._unsub_refresh = self.hass.helpers.event.async_track_time_interval(
            self._handle_refresh_interval, self.update_interval
        )
        self.logger.debug(f"Scheduled next refresh in {self.scan_interval} seconds")

    async def _handle_refresh_interval(self, _now=None):
        """Handle a refresh interval occurring."""
        self.logger.debug(f"Regular interval refresh for {self.address}")
        await self.async_request_refresh()

    def async_start(self) -> Callable[[], None]:
        """Start polling."""
        self.logger.info("Starting polling for device %s", self.address)

        def _unsub() -> None:
            """Unsubscribe from updates."""
            if self._unsub_refresh:
                self._unsub_refresh()
                self._unsub_refresh = None

        _unsub()  # Cancel any previous subscriptions

        # We use the active update coordinator's start method
        # which already handles the bluetooth subscriptions
        result = super().async_start()

        # Schedule regular refreshes at our configured interval
        self._schedule_refresh()

        # Perform an initial refresh to get data as soon as possible
        self.hass.async_create_task(self.async_request_refresh())

        return result

    def async_stop(self) -> None:
        """Stop polling."""
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None

        # Call the parent class's stop method
        super().async_stop()

    @callback
    def _needs_poll(
        self,
        service_info: BluetoothServiceInfoBleak,
        last_poll: float | None,
    ) -> bool:
        """Determine if device needs polling based on time since last poll."""
        # Only poll if hass is running and device is connectable
        if self.hass.state != CoreState.running:
            return False

        # Check if we have a connectable device
        connectable_device = bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        )
        if not connectable_device:
            self.logger.warning(
                f"No connectable device found for {service_info.address}"
            )
            return False

        # If a connection is already in progress, don't start another one
        if self._connection_in_progress:
            self.logger.debug("Connection already in progress, skipping poll")
            return False

        # If we've never polled or it's been longer than the scan interval, poll
        if last_poll is None:
            self.logger.debug(f"First poll for device {service_info.address}")
            return True

        # Check if enough time has elapsed since the last poll
        time_since_poll = datetime.now().timestamp() - last_poll
        should_poll = time_since_poll >= self.scan_interval

        if should_poll:
            self.logger.debug(
                f"Time to poll device {service_info.address} after {time_since_poll:.1f}s"
            )

        return should_poll

    async def _read_device_data(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Read data from a Renogy BLE device using active connection."""
        async with self._connection_lock:
            try:
                self._connection_in_progress = True

                # Use service_info to get a BLE device and update our device object
                if not self.device:
                    self.logger.info(
                        f"Creating new RenogyBLEDevice for {service_info.address}"
                    )
                    self.device = RenogyBLEDevice(service_info.device)
                else:
                    # Store the old name to detect changes
                    old_name = self.device.name

                    self.device.ble_device = service_info.device
                    # Update name if available from service_info
                    if (
                        service_info.name
                        and service_info.name != "Unknown Renogy Device"
                    ):
                        self.device.name = service_info.name
                        if old_name != service_info.name:
                            self.logger.info(
                                f"Updated device name from '{old_name}' to '{service_info.name}'"
                            )

                    # Prefer the RSSI from advertisement data if available
                    self.device.rssi = (
                        service_info.advertisement.rssi
                        if service_info.advertisement
                        and service_info.advertisement.rssi is not None
                        else service_info.device.rssi
                    )

                device = self.device
                self.logger.info(f"Polling device: {device.name} ({device.address})")
                success = False

                async with BleakClient(service_info.device) as client:
                    any_command_succeeded = False

                    try:
                        self.logger.debug(f"Connecting to device {device.name}")
                        await client.connect()
                        if client.is_connected:
                            self.logger.info(f"Connected to device {device.name}")

                            # Create an event that will be set when notification data is received
                            notification_event = asyncio.Event()
                            notification_data = bytearray()

                            def notification_handler(sender, data):
                                notification_data.extend(data)
                                notification_event.set()

                            await client.start_notify(
                                RENOGY_READ_CHAR_UUID, notification_handler
                            )

                            for cmd_name, cmd in commands.items():
                                notification_data.clear()
                                notification_event.clear()

                                modbus_request = create_modbus_read_request(
                                    default_device_id, *cmd
                                )
                                self.logger.debug(
                                    f"Sending {cmd_name} command: {list(modbus_request)}"
                                )
                                await client.write_gatt_char(
                                    RENOGY_WRITE_CHAR_UUID, modbus_request
                                )

                                try:
                                    await asyncio.wait_for(
                                        notification_event.wait(),
                                        MAX_NOTIFICATION_WAIT_TIME,
                                    )
                                except asyncio.TimeoutError:
                                    self.logger.warning(
                                        f"Timeout waiting for {cmd_name} data from device {device.name}"
                                    )
                                    continue

                                result_data = bytes(notification_data)
                                self.logger.debug(
                                    f"Received {cmd_name} data length: {len(result_data)}"
                                )

                                cmd_success = device.update_parsed_data(
                                    result_data, register=cmd[1], cmd_name=cmd_name
                                )

                                if cmd_success:
                                    self.logger.info(
                                        f"Successfully read and parsed {cmd_name} data from device {device.name}"
                                    )
                                    any_command_succeeded = True
                                else:
                                    self.logger.warning(
                                        f"Failed to parse {cmd_name} data from device {device.name}"
                                    )

                            await client.stop_notify(RENOGY_READ_CHAR_UUID)
                            success = any_command_succeeded
                        else:
                            self.logger.warning(
                                f"Failed to connect to device {device.name}"
                            )
                    except Exception as e:
                        self.logger.error(
                            f"Error reading data from device {device.name}: {str(e)}"
                        )
                    finally:
                        if client and client.is_connected:
                            try:
                                await client.disconnect()
                                self.logger.debug(
                                    f"Disconnected from device {device.name}"
                                )
                            except Exception as e:
                                self.logger.warning(
                                    f"Error disconnecting from device {device.name}: {str(e)}"
                                )

                device.update_availability(success)
                self.last_update_success = success

                if success and device.parsed_data:
                    self.data = dict(device.parsed_data)
                    self.logger.debug(f"Updated coordinator data: {self.data}")

                return success
            finally:
                self._connection_in_progress = False

    async def _async_poll(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Poll the device."""
        # If a connection is already in progress, don't start another one
        if self._connection_in_progress:
            self.logger.debug("Connection already in progress, skipping poll")
            return

        self.last_poll_time = datetime.now()
        self.logger.info(
            f"Polling device: {service_info.name} ({service_info.address})"
        )

        # Read device data using service_info and Home Assistant's Bluetooth API
        success = await self._read_device_data(service_info)

        if success and self.device and self.device.parsed_data:
            # Log the parsed data for debugging
            self.logger.debug(f"Parsed data: {self.device.parsed_data}")

            # Call the callback if available
            if self.device_data_callback:
                try:
                    self.hass.async_create_task(self.device_data_callback(self.device))
                except Exception as e:
                    self.logger.error(f"Error in device data callback: {str(e)}")

            # Update all listeners after successful data acquisition
            self.async_update_listeners()

        else:
            self.logger.warning(f"No data retrieved from device {service_info.address}")
            self.last_update_success = False

    @callback
    def _async_handle_unavailable(
        self, service_info: BluetoothServiceInfoBleak
    ) -> None:
        """Handle the device going unavailable."""
        self.logger.info(f"Device {service_info.address} is no longer available")
        if self.device:
            self.device.update_availability(False)
        self.last_update_success = False
        self.async_update_listeners()

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Handle a Bluetooth event."""
        # Update RSSI if device exists
        if self.device:
            self.device.rssi = service_info.advertisement.rssi
            self.device.last_seen = datetime.now()
