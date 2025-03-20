"""Tests for the BLE module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.renogy_ha.ble import RenogyBLEClient, RenogyBLEDevice
from custom_components.renogy_ha.const import RENOGY_BT_PREFIX


@pytest.fixture
def mock_ble_device_bt1():
    """Create a mock BLE device with BT module identifier."""
    device = MagicMock()
    device.name = f"{RENOGY_BT_PREFIX}7724620D"
    device.address = "AA:BB:CC:DD:EE:FF"
    device.rssi = -60
    # Make the device behave like a BLEDevice without using spec
    device.__str__ = lambda self: self.address
    device.__repr__ = lambda self: self.address
    return device


@pytest.fixture
def mock_non_renogy_device():
    """Create a mock non-Renogy BLE device."""
    device = MagicMock()
    device.name = "SomeOtherDevice"
    device.address = "99:88:77:66:55:44"
    device.rssi = -70
    return device


@pytest.fixture
def mock_renogy_device(mock_ble_device_bt1):
    """Create a mock RenogyBLEDevice instance."""
    return RenogyBLEDevice(mock_ble_device_bt1)


class TestRenogyBLEClient:
    """Test the RenogyBLEClient class."""

    @pytest.mark.asyncio
    async def test_is_renogy_device(self, mock_ble_device_bt1, mock_non_renogy_device):
        """Test the is_renogy_device method."""
        client = RenogyBLEClient()

        # Test BT-1 and BT-2 devices
        assert client.is_renogy_device(mock_ble_device_bt1) is True

        # Test non-Renogy device
        assert client.is_renogy_device(mock_non_renogy_device) is False

        # Test device with no name
        nameless_device = MagicMock()
        nameless_device.name = None
        assert client.is_renogy_device(nameless_device) is False

    @pytest.mark.asyncio
    async def test_scan_for_devices(self, mock_ble_device_bt1, mock_non_renogy_device):
        """Test scanning for devices."""
        client = RenogyBLEClient()

        # Mock the discover method to return our test devices
        with patch(
            "bleak.BleakScanner.discover",
            return_value=[mock_ble_device_bt1, mock_non_renogy_device],
        ):
            devices = await client.scan_for_devices()

            # Should find 1 Renogy device
            assert len(devices) == 1

            # Check that the devices were correctly identified
            device_addresses = [device.address for device in devices]
            assert mock_ble_device_bt1.address in device_addresses
            assert mock_non_renogy_device.address not in device_addresses

    @pytest.mark.asyncio
    async def test_scan_exception_handling(self):
        """Test exception handling during scanning."""
        client = RenogyBLEClient()

        # Mock the discover method to raise an exception
        with patch("bleak.BleakScanner.discover", side_effect=Exception("Test error")):
            devices = await client.scan_for_devices()

            # Should return an empty list when an exception occurs
            assert len(devices) == 0

    @pytest.mark.asyncio
    async def test_polling_starts_and_stops(self):
        """Test that polling starts and stops correctly."""
        client = RenogyBLEClient(scan_interval=0.1)  # Short interval for testing

        # Mock scan_for_devices to return an empty list of devices
        with patch.object(client, "scan_for_devices", return_value=[]):
            # Start polling
            await client.start_polling()
            assert client._running is True
            assert client._scan_task is not None

            # Wait briefly to ensure the polling loop runs at least once
            await asyncio.sleep(0.2)

            # Stop polling
            await client.stop_polling()
            assert client._running is False
            assert client._scan_task is None

    @pytest.mark.asyncio
    async def test_read_device_data(self, mock_renogy_device):
        """Test reading data from a device."""
        client = RenogyBLEClient()

        # Mock BleakClient to simulate BLE communication
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()

        # Setup mock data
        device_info_data = bytes([0x09, 0x0A, 0x0B, 0x0C])  # Mock device info data
        device_id_data = bytes([0x0D, 0x0E, 0x0F, 0x10])  # Mock device id data
        battery_data = bytes([0x01, 0x02, 0x03, 0x04])  # Mock battery data
        pv_data = bytes([0x05, 0x06, 0x07, 0x08])  # Mock PV data

        # Variable to store notification handler
        notification_handler = None

        # Mock start_notify to capture the notification handler
        async def mock_start_notify(char_uuid, handler):
            nonlocal notification_handler
            notification_handler = handler

        # Simulate write_gatt_char triggering different notifications based on command
        async def mock_write_gatt_char(char_uuid, command):
            # Let's identify which command is being sent based on a pattern
            await asyncio.sleep(0)  # Small delay to allow async flow

            if b"\xe0\x04" in command:  # battery command
                notification_handler(0, battery_data)
            elif b"\x01\x00" in command:  # pv command
                notification_handler(0, pv_data)
            elif b"\x00\x0c" in command:  # device info command
                notification_handler(0, device_info_data)
            elif b"\x00\x1a" in command:  # device id command
                notification_handler(0, device_id_data)

        mock_client.start_notify = AsyncMock(side_effect=mock_start_notify)
        mock_client.write_gatt_char = AsyncMock(side_effect=mock_write_gatt_char)
        mock_client.stop_notify = AsyncMock()

        # Mock the update_parsed_data method
        mock_renogy_device.update_parsed_data = MagicMock(return_value=True)

        # Create a BleakClient mock that returns our mock client
        def mock_bleak_client_init(device, *args, **kwargs):
            return mock_client

        # Mock commands dictionary
        mock_commands = {
            "device_info": (3, 12, 8),
            "device_id": (3, 26, 1),
            "battery": (3, 57348, 1),
            "pv": (3, 256, 34),
        }

        # Patch what's needed for testing
        with (
            patch(
                "custom_components.renogy_ha.ble.BleakClient",
                side_effect=mock_bleak_client_init,
            ),
            patch(
                "custom_components.renogy_ha.ble.commands",
                mock_commands,
            ),
            patch("asyncio.sleep", AsyncMock()),
        ):
            # Call the method being tested
            success = await client.read_device_data(mock_renogy_device)

            # Verify the result was successful
            assert success is True

            # Check that update_parsed_data was called once with register parameter
            assert mock_renogy_device.update_parsed_data.call_count >= 1

            # Verify the connection was established and then closed
            mock_client.connect.assert_called_once()
            mock_client.disconnect.assert_called_once()

            # Verify other method calls
            assert mock_client.start_notify.called
            assert mock_client.stop_notify.called
            assert mock_client.write_gatt_char.call_count > 0

    @pytest.mark.asyncio
    async def test_read_device_data_connection_failure(self, mock_renogy_device):
        """Test handling of connection failure during data reading."""
        client = RenogyBLEClient()

        # Mock BleakClient to simulate connection failure
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(side_effect=Exception("Connection failed"))

        with patch("bleak.BleakClient", return_value=mock_client):
            success = await client.read_device_data(mock_renogy_device)

            # Verify the result was not successful
            assert success is False

            # Check that the availability was updated
            assert mock_renogy_device.failure_count == 1


class TestRenogyBLEDevice:
    """Test the RenogyBLEDevice class."""

    def test_device_initialization(self, mock_ble_device_bt1):
        """Test device initialization."""
        device = RenogyBLEDevice(mock_ble_device_bt1)

        # Verify the initial state
        assert device.address == mock_ble_device_bt1.address
        assert device.name == mock_ble_device_bt1.name
        assert device.rssi == mock_ble_device_bt1.rssi
        assert device.available is True
        assert device.failure_count == 0
        assert device.parsed_data == {}
        assert device.model == "rover"

    def test_update_availability(self, mock_renogy_device):
        """Test the update_availability method."""
        # Test successful update
        mock_renogy_device.available = False
        mock_renogy_device.failure_count = 3
        mock_renogy_device.update_availability(True)

        assert mock_renogy_device.available is True
        assert mock_renogy_device.failure_count == 0

        # Test failed update
        mock_renogy_device.update_availability(False)
        assert mock_renogy_device.failure_count == 1
        assert (
            mock_renogy_device.available is True
        )  # Still true until max_failures reached

        # Test reaching max failures
        mock_renogy_device.max_failures = 3
        mock_renogy_device.update_availability(False)  # 2 failures
        mock_renogy_device.update_availability(False)  # 3 failures

        assert mock_renogy_device.failure_count == 3
        assert mock_renogy_device.available is False

    def test_is_available(self, mock_renogy_device):
        """Test the is_available property."""
        mock_renogy_device.available = True
        mock_renogy_device.failure_count = 0
        assert mock_renogy_device.is_available is True

        mock_renogy_device.available = False
        assert mock_renogy_device.is_available is False

        mock_renogy_device.available = True
        mock_renogy_device.failure_count = mock_renogy_device.max_failures
        assert mock_renogy_device.is_available is False

    @patch("custom_components.renogy_ha.ble.RenogyParser")
    def test_update_parsed_data(self, mock_renogy_parser, mock_renogy_device):
        """Test the update_parsed_data method."""
        # Mock the RenogyParser.parse method
        mock_parsed_data = {
            "battery_voltage": 12.6,
            "battery_current": 1.5,
            "battery_percentage": 85,
            "pv_voltage": 18.0,
            "pv_current": 2.5,
            "pv_power": 45,
            "charging_status": "mppt",
        }
        register = 256
        mock_renogy_parser.parse.return_value = mock_parsed_data

        # Create some test raw data
        raw_data = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06])

        # Test successful parsing
        result = mock_renogy_device.update_parsed_data(raw_data, register)
        assert result is True
        assert mock_renogy_device.parsed_data == mock_parsed_data

        # Verify the parser was called correctly with all three parameters
        mock_renogy_parser.parse.assert_called_once_with(
            raw_data, mock_renogy_device.model, register
        )

        # Test handling of empty parse result
        mock_renogy_parser.parse.return_value = {}
        result = mock_renogy_device.update_parsed_data(raw_data, register)
        assert result is False

        # Test handling of parser exception
        mock_renogy_parser.parse.side_effect = Exception("Parse error")
        result = mock_renogy_device.update_parsed_data(raw_data, register)
        assert result is False

    @patch("custom_components.renogy_ha.ble.RenogyParser", None)
    def test_update_parsed_data_no_parser(self, mock_renogy_device):
        """Test update_parsed_data when RenogyParser is not available."""
        raw_data = bytes([0x01, 0x02, 0x03, 0x04])
        result = mock_renogy_device.update_parsed_data(raw_data, register=256)
        assert result is False

    def test_availability_after_consecutive_failures(self, mock_renogy_device):
        """Test device availability after consecutive failures."""
        # Initial state should be available
        assert mock_renogy_device.available is True
        assert mock_renogy_device.is_available is True

        # First failure
        mock_renogy_device.update_availability(False)
        assert mock_renogy_device.failure_count == 1
        assert mock_renogy_device.available is True
        assert mock_renogy_device.is_available is True

        # Second failure
        mock_renogy_device.update_availability(False)
        assert mock_renogy_device.failure_count == 2
        assert mock_renogy_device.available is True
        assert mock_renogy_device.is_available is True

        # Third failure - should mark device as unavailable
        mock_renogy_device.update_availability(False)
        assert mock_renogy_device.failure_count == 3
        assert mock_renogy_device.available is False
        assert mock_renogy_device.is_available is False

        # Fourth failure - should keep device unavailable
        mock_renogy_device.update_availability(False)
        assert mock_renogy_device.failure_count == 4
        assert mock_renogy_device.available is False
        assert mock_renogy_device.is_available is False

    def test_recovery_after_failures(self, mock_renogy_device):
        """Test device recovery after previous failures."""
        # Set initial state to unavailable after failures
        mock_renogy_device.failure_count = 4
        mock_renogy_device.available = False
        assert mock_renogy_device.is_available is False

        # Successful communication should reset failure count and make device available
        mock_renogy_device.update_availability(True)
        assert mock_renogy_device.failure_count == 0
        assert mock_renogy_device.available is True
        assert mock_renogy_device.is_available is True


class TestRenogyBLEClientErrorHandling:
    """Test error handling in the RenogyBLEClient class."""

    @pytest.mark.asyncio
    async def test_consecutive_failures_in_polling(self, mock_renogy_device):
        """Test the behavior when consecutive failures occur in the polling loop."""
        client = RenogyBLEClient(scan_interval=0.1)  # Short interval for testing

        # Mock scan_for_devices to return our device
        with (
            patch.object(client, "scan_for_devices", return_value=[mock_renogy_device]),
            patch.object(
                client, "read_device_data", side_effect=[False, False, False, True]
            ),
        ):
            # Add the device to discovered devices
            client.discovered_devices[mock_renogy_device.address] = mock_renogy_device

            # Start polling
            await client.start_polling()

            # Wait for 4 polling cycles (3 failures followed by 1 success)
            await asyncio.sleep(0.5)

            # Stop polling
            await client.stop_polling()

            # Verify the device went unavailable after 3 failures and then available again
            assert mock_renogy_device.failure_count == 0  # Reset after success
            assert mock_renogy_device.available is True

    @pytest.mark.asyncio
    async def test_device_skipped_when_unavailable(self, mock_renogy_device):
        """Test that unavailable devices are skipped in the polling loop."""
        client = RenogyBLEClient()

        # Mark device as unavailable
        mock_renogy_device.available = False
        mock_renogy_device.failure_count = 3

        # Should return False without attempting to connect
        success = await client.read_device_data(mock_renogy_device)
        assert success is False

        # Create a mock BleakClient to verify it wasn't called
        with patch("bleak.BleakClient") as mock_bleak_client:
            await client.read_device_data(mock_renogy_device)
            mock_bleak_client.assert_not_called()
