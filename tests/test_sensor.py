"""Tests for the sensor module."""

from unittest.mock import MagicMock

import pytest

# Import the module we need to test
from custom_components.renogy_ha.ble import RenogyBLEDevice
from custom_components.renogy_ha.sensor import (
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
