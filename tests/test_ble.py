"""Tests for the BLE module."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock

from custom_components.renogy_ha.ble import RenogyBLEClient, RenogyBLEDevice
from custom_components.renogy_ha.const import RENOGY_BT_PREFIX


@pytest.fixture
def mock_ble_device_bt1():
    """Create a mock BLE device with BT module identifier."""
    device = MagicMock()
    device.name = f"{RENOGY_BT_PREFIX}7724620D"
    device.address = "AA:BB:CC:DD:EE:FF"
    device.rssi = -60
    return device

@pytest.fixture
def mock_non_renogy_device():
    """Create a mock non-Renogy BLE device."""
    device = MagicMock()
    device.name = "SomeOtherDevice"
    device.address = "99:88:77:66:55:44"
    device.rssi = -70
    return device


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
        with patch('bleak.BleakScanner.discover', return_value=[
            mock_ble_device_bt1, mock_non_renogy_device
        ]):
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
        with patch('bleak.BleakScanner.discover', side_effect=Exception("Test error")):
            devices = await client.scan_for_devices()
            
            # Should return an empty list when an exception occurs
            assert len(devices) == 0

    @pytest.mark.asyncio
    async def test_polling_starts_and_stops(self):
        """Test that polling starts and stops correctly."""
        client = RenogyBLEClient(scan_interval=0.1)  # Short interval for testing
        
        # Mock scan_for_devices to return an empty list of devices
        with patch.object(client, 'scan_for_devices', return_value=[]):
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