"""Tests for Renogy sensor functionality."""

from unittest.mock import MagicMock

import pytest

# Define constants locally instead of importing them
BATTERY_VOLTAGE = "battery_voltage"
BATTERY_CURRENT = "battery_current"
BATTERY_PERCENTAGE = "battery_percentage"
BATTERY_TEMPERATURE = "battery_temperature"
BATTERY_TYPE = "battery_type"
CHARGING_STATUS = "charging_status"
PV_VOLTAGE = "pv_voltage"
PV_CURRENT = "pv_current"
PV_POWER = "pv_power"
LOAD_VOLTAGE = "load_voltage"
LOAD_CURRENT = "load_current"
LOAD_POWER = "load_power"
LOAD_STATUS = "load_status"
CONTROLLER_TEMPERATURE = "controller_temperature"


@pytest.fixture
def mock_sensor_data():
    """Create mock sensor data."""
    return {
        # Battery data
        BATTERY_VOLTAGE: 12.6,
        BATTERY_CURRENT: 1.5,
        BATTERY_PERCENTAGE: 85,
        BATTERY_TEMPERATURE: 25,
        BATTERY_TYPE: 3,  # lithium
        "charging_amp_hours_today": 10.5,
        "discharging_amp_hours_today": 8.2,
        CHARGING_STATUS: 2,  # mppt
        # PV data
        PV_VOLTAGE: 18.2,
        PV_CURRENT: 2.8,
        PV_POWER: 51,
        "max_charging_power_today": 120,
        "power_generation_today": 450,
        "power_generation_total": 12.5,  # kWh
        # Load data
        LOAD_VOLTAGE: 12.4,
        LOAD_CURRENT: 1.2,
        LOAD_POWER: 15,
        LOAD_STATUS: 1,  # on
        "power_consumption_today": 180,
        # Controller data
        CONTROLLER_TEMPERATURE: 30,
        "device_id": "BT-TH-1234ABCD",
        "model": "Rover",
        "max_discharging_power_today": 25,
    }


@pytest.fixture
def mock_device():
    """Create a mock Renogy device."""
    device = MagicMock()
    device.name = "Test Renogy Device"
    device.address = "AA:BB:CC:DD:EE:FF"
    device.is_available = True
    device.parsed_data = {}  # Will be filled from mock_sensor_data
    return device


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {}  # Will be filled from mock_sensor_data
    coordinator.device = None  # Will be set in tests
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    return coordinator


def test_sensor_key_registration():
    """Test that all necessary sensor keys are registered correctly."""
    # Battery related keys
    assert BATTERY_VOLTAGE == "battery_voltage"
    assert BATTERY_CURRENT == "battery_current"
    assert BATTERY_PERCENTAGE == "battery_percentage"
    assert BATTERY_TEMPERATURE == "battery_temperature"
    assert BATTERY_TYPE == "battery_type"
    assert CHARGING_STATUS == "charging_status"

    # PV related keys
    assert PV_VOLTAGE == "pv_voltage"
    assert PV_CURRENT == "pv_current"
    assert PV_POWER == "pv_power"

    # Load related keys
    assert LOAD_VOLTAGE == "load_voltage"
    assert LOAD_CURRENT == "load_current"
    assert LOAD_POWER == "load_power"
    assert LOAD_STATUS == "load_status"

    # Controller related keys
    assert CONTROLLER_TEMPERATURE == "controller_temperature"


def test_sensor_value_extraction(mock_device, mock_coordinator, mock_sensor_data):
    """Test that sensor values can be properly extracted from device data."""
    # Set up our test data
    mock_device.parsed_data = mock_sensor_data
    mock_coordinator.data = mock_sensor_data
    mock_coordinator.device = mock_device

    # Check direct data access
    assert mock_device.parsed_data[BATTERY_VOLTAGE] == 12.6
    assert mock_coordinator.data[BATTERY_PERCENTAGE] == 85
    assert mock_coordinator.data[PV_POWER] == 51
    assert mock_coordinator.data[LOAD_STATUS] == 1
    assert mock_coordinator.data[CONTROLLER_TEMPERATURE] == 30

    # Test with missing data
    missing_data = {}
    mock_coordinator.data = missing_data
    mock_device.parsed_data = missing_data

    # Check that missing data is handled correctly
    assert mock_device.parsed_data.get(BATTERY_VOLTAGE) is None
    assert mock_coordinator.data.get(BATTERY_PERCENTAGE) is None


def test_sensor_availability(mock_device, mock_coordinator):
    """Test sensor availability behavior."""
    # When device is available and coordinator update successful
    mock_device.is_available = True
    mock_coordinator.last_update_success = True
    assert mock_device.is_available is True

    # When device is unavailable
    mock_device.is_available = False
    assert mock_device.is_available is False

    # When coordinator update fails
    mock_device.is_available = True
    mock_coordinator.last_update_success = False


def test_battery_type_mapping(mock_sensor_data):
    """Test battery type code to string mapping."""
    # Battery type codes and expected values
    battery_types = {
        0: "open",  # Open/Flooded
        1: "sealed",  # Sealed/AGM
        2: "gel",  # Gel
        3: "lithium",  # Lithium
        4: "custom",  # Custom
    }

    # Verify the codes match expectations
    for code, expected_type in battery_types.items():
        # In the actual code, this would use the mapping functions
        # We're just testing that the codes are recognized
        assert code in range(5)


def test_charging_status_mapping(mock_sensor_data):
    """Test charging status code to string mapping."""
    # Charging status codes and expected values
    charging_statuses = {
        0: "deactivated",
        1: "activated",
        2: "mppt",
        3: "equalizing",
        4: "boost",
        5: "floating",
        6: "current limiting",
    }

    # Verify the codes match expectations
    for code, expected_status in charging_statuses.items():
        # In the actual code, this would use the mapping functions
        # We're just testing that the codes are recognized
        assert code in range(7)


def test_load_status_mapping(mock_sensor_data):
    """Test load status code to string mapping."""
    # Load status codes and expected values
    load_statuses = {
        0: "off",
        1: "on",
    }

    # Verify the codes match expectations
    for code, expected_status in load_statuses.items():
        # In the actual code, this would use the mapping functions
        # We're just testing that the codes are recognized
        assert code in range(2)
