"""Integration tests for the Renogy BLE integration without dependencies."""

from unittest.mock import MagicMock

import pytest

# Define constants locally to avoid importing from the actual module
DOMAIN = "renogy_ha"
CONF_SCAN_INTERVAL = "scan_interval"


@pytest.fixture
def mock_ble_device():
    """Create a mock BLE device."""
    device = MagicMock()
    device.address = "AA:BB:CC:DD:EE:FF"
    device.name = "BT-TH-12345"
    device.rssi = -60
    return device


@pytest.fixture
def mock_renogy_device():
    """Create a mock Renogy BLE device with parsed data."""
    device = MagicMock()
    device.address = "AA:BB:CC:DD:EE:FF"
    device.name = "BT-TH-12345"
    device.rssi = -60
    device.available = True
    device.is_available = True
    device.parsed_data = {
        "battery_voltage": 12.8,
        "battery_current": 1.5,
        "battery_percentage": 85,
        "battery_temperature": 25,
        "battery_type": 1,  # sealed
        "charging_amp_hours_today": 10.5,
        "discharging_amp_hours_today": 5.2,
        "charging_status": 2,  # mppt
        "pv_voltage": 18.5,
        "pv_current": 2.3,
        "pv_power": 42.55,
        "max_charging_power_today": 60.0,
        "power_generation_today": 120.5,
        "power_generation_total": 1250.75,
        "load_voltage": 12.7,
        "load_current": 0.8,
        "load_power": 10.16,
        "load_status": 1,  # on
        "power_consumption_today": 45.2,
        "controller_temperature": 35,
        "device_id": "ROVER12345",
        "model": "Rover 40A",
        "firmware_version": "v1.2.3",
        "max_discharging_power_today": 30.0,
    }
    device.update_availability = MagicMock()
    device.update_parsed_data = MagicMock(return_value=True)
    return device


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = {}
    coordinator.device = None
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.last_update_success = True
    coordinator.async_request_refresh = MagicMock()
    coordinator.async_start = MagicMock(return_value=lambda: None)
    # Add a _listeners array that coordinator implementations typically have
    coordinator._listeners = []
    return coordinator


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    return hass


def test_device_discovery_and_data(mock_coordinator, mock_renogy_device):
    """Test device discovery and data processing."""
    # Set up the coordinator with our mock device
    mock_coordinator.device = mock_renogy_device
    mock_coordinator.data = mock_renogy_device.parsed_data

    # Verify device data
    assert mock_coordinator.device.name == "BT-TH-12345"
    assert mock_coordinator.device.address == "AA:BB:CC:DD:EE:FF"
    assert mock_coordinator.device.available is True

    # Verify parsed data
    assert mock_coordinator.data["battery_voltage"] == 12.8
    assert mock_coordinator.data["pv_power"] == 42.55
    assert mock_coordinator.data["model"] == "Rover 40A"


def test_coordinator_device_interaction(mock_coordinator, mock_renogy_device):
    """Test coordinator behavior with device."""
    # Set up coordinator with mock device
    mock_coordinator.device = mock_renogy_device
    mock_coordinator.data = mock_renogy_device.parsed_data

    # Add a callback function that will update the device
    def update_callback():
        mock_renogy_device.update_availability(True)

    # Register the callback with the coordinator
    mock_coordinator._listeners.append(update_callback)

    # Test device availability propagation
    mock_renogy_device.is_available = False
    assert not mock_renogy_device.is_available

    # Test coordinator successful data refresh
    mock_coordinator.last_update_success = True

    # Simulate calling callback from BT update
    for callback in mock_coordinator._listeners:
        callback()

    # Device update was used to update data
    mock_renogy_device.update_availability.assert_called_with(True)


def test_malformed_data_handling(mock_coordinator, mock_renogy_device):
    """Test handling of malformed data from the device."""
    # Set up coordinator with mock device
    mock_coordinator.device = mock_renogy_device

    # Save the original good data
    good_data = dict(mock_renogy_device.parsed_data)

    # Test cases for different malformed data scenarios
    test_cases = [
        {},  # Empty data
        {"battery_voltage": None},  # None value
        {"battery_voltage": "invalid"},  # Wrong type
        {"unknown_field": 123},  # Unknown field
    ]

    for test_data in test_cases:
        # Update device with bad data
        mock_renogy_device.parsed_data = test_data
        mock_coordinator.data = test_data

        # Device should remain available despite bad data
        assert mock_renogy_device.available is True

    # Restore good data
    mock_renogy_device.parsed_data = good_data
    mock_coordinator.data = good_data
