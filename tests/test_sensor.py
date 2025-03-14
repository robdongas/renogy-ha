"""Tests for the sensor module."""

from unittest.mock import MagicMock

import pytest

# Import the module we need to test
from custom_components.renogy_ha.ble import RenogyBLEDevice
from custom_components.renogy_ha.sensor import (
    BATTERY_TYPES,
    CHARGING_STATUSES,
    KEY_BATTERY_CURRENT,
    KEY_BATTERY_PERCENTAGE,
    KEY_BATTERY_TEMPERATURE,
    KEY_BATTERY_TYPE,
    KEY_BATTERY_VOLTAGE,
    KEY_CHARGING_STATUS,
    KEY_CONTROLLER_TEMPERATURE,
    KEY_LOAD_CURRENT,
    KEY_LOAD_POWER,
    KEY_LOAD_STATUS,
    KEY_LOAD_VOLTAGE,
    KEY_PV_CURRENT,
    KEY_PV_POWER,
    KEY_PV_VOLTAGE,
    LOAD_STATUSES,
)


@pytest.fixture
def mock_device():
    """Create a mock Renogy BLE device."""
    device = MagicMock(spec=RenogyBLEDevice)
    device.name = "Test Renogy Device"
    device.address = "AA:BB:CC:DD:EE:FF"
    device.is_available = True
    device.parsed_data = {
        # Battery data
        KEY_BATTERY_VOLTAGE: 12.6,
        KEY_BATTERY_CURRENT: 1.5,
        KEY_BATTERY_PERCENTAGE: 85,
        KEY_BATTERY_TEMPERATURE: 25,
        KEY_BATTERY_TYPE: 3,  # lithium
        "charging_amp_hours_today": 10.5,
        "discharging_amp_hours_today": 8.2,
        KEY_CHARGING_STATUS: 2,  # mppt
        # PV data
        KEY_PV_VOLTAGE: 18.2,
        KEY_PV_CURRENT: 2.8,
        KEY_PV_POWER: 51,
        "max_charging_power_today": 120,
        "power_generation_today": 450,
        "power_generation_total": 12.5,  # kWh
        # Load data
        KEY_LOAD_VOLTAGE: 12.4,
        KEY_LOAD_CURRENT: 1.2,
        KEY_LOAD_POWER: 15,
        KEY_LOAD_STATUS: 1,  # on
        "power_consumption_today": 180,
        # Controller data
        KEY_CONTROLLER_TEMPERATURE: 30,
        "device_id": "BT-TH-1234ABCD",
        "model": "Rover",
        "max_discharging_power_today": 25,
    }
    return device


def test_battery_type_mapping():
    """Test the battery type text mapping."""
    assert BATTERY_TYPES[0] == "open"
    assert BATTERY_TYPES[1] == "sealed"
    assert BATTERY_TYPES[2] == "gel"
    assert BATTERY_TYPES[3] == "lithium"
    assert BATTERY_TYPES[4] == "custom"


def test_charging_status_mapping():
    """Test the charging status text mapping."""
    assert CHARGING_STATUSES[0] == "deactivated"
    assert CHARGING_STATUSES[1] == "activated"
    assert CHARGING_STATUSES[2] == "mppt"
    assert CHARGING_STATUSES[3] == "equalizing"
    assert CHARGING_STATUSES[4] == "boost"
    assert CHARGING_STATUSES[5] == "floating"
    assert CHARGING_STATUSES[6] == "current limiting"


def test_load_status_mapping():
    """Test the load status text mapping."""
    assert LOAD_STATUSES[0] == "off"
    assert LOAD_STATUSES[1] == "on"


def test_sensor_key_registration():
    """Test that all necessary sensor keys are registered."""
    # Battery related keys
    assert KEY_BATTERY_VOLTAGE == "battery_voltage"
    assert KEY_BATTERY_CURRENT == "battery_current"
    assert KEY_BATTERY_PERCENTAGE == "battery_percentage"
    assert KEY_BATTERY_TEMPERATURE == "battery_temperature"
    assert KEY_BATTERY_TYPE == "battery_type"
    assert KEY_CHARGING_STATUS == "charging_status"

    # PV related keys
    assert KEY_PV_VOLTAGE == "pv_voltage"
    assert KEY_PV_CURRENT == "pv_current"
    assert KEY_PV_POWER == "pv_power"

    # Load related keys
    assert KEY_LOAD_VOLTAGE == "load_voltage"
    assert KEY_LOAD_CURRENT == "load_current"
    assert KEY_LOAD_POWER == "load_power"
    assert KEY_LOAD_STATUS == "load_status"

    # Controller related keys
    assert KEY_CONTROLLER_TEMPERATURE == "controller_temperature"
