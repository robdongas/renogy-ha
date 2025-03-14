"""Integration tests for the Renogy BLE integration."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.core import HomeAssistant

from custom_components.renogy_ha.ble import RenogyBLEDevice
from custom_components.renogy_ha.const import CONF_SCAN_INTERVAL, DOMAIN


@pytest.fixture
def mock_ble_device():
    """Create a mock BLE device."""
    device = MagicMock(spec=BLEDevice)
    device.address = "AA:BB:CC:DD:EE:FF"
    device.name = "BT-TH-12345"
    device.rssi = -60
    return device


@pytest.fixture
def mock_renogy_device(mock_ble_device):
    """Create a mock Renogy BLE device with parsed data."""
    device = RenogyBLEDevice(mock_ble_device)
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
    device.available = True
    return device


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return MagicMock(
        domain=DOMAIN,
        data={CONF_SCAN_INTERVAL: 30},
        entry_id="test",
        title="Renogy BLE",
    )


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance for testing."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.config_entries = MagicMock()
    # Use AsyncMock for async_forward_entry_setups
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.async_create_task = lambda task: asyncio.create_task(task)
    hass.async_add_executor_job = MagicMock()
    hass.data.setdefault(DOMAIN, {})
    return hass


@pytest.mark.asyncio
async def test_device_discovery_and_registration(
    mock_hass, mock_config_entry, mock_renogy_device
):
    """Test device is properly registered and sensors are created."""
    # Mock the __init__.py functions, particularly the BLE client
    with patch(
        "custom_components.renogy_ha.RenogyDataUpdateCoordinator"
    ) as mock_coordinator_class:
        # Set up the coordinator mock
        mock_coordinator = MagicMock()
        mock_coordinator_class.return_value = mock_coordinator

        # Mock the devices dictionary
        mock_coordinator.devices = {mock_renogy_device.address: mock_renogy_device}

        # Mock the async_config_entry_first_refresh method
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.start_polling = AsyncMock()

        # Call the async_setup_entry function from __init__.py
        from custom_components.renogy_ha import async_setup_entry

        assert await async_setup_entry(mock_hass, mock_config_entry)

        # Verify the coordinator was properly initialized
        mock_coordinator_class.assert_called_once_with(
            mock_hass, mock_config_entry.data[CONF_SCAN_INTERVAL]
        )

        # Ensure platforms were set up
        assert mock_hass.config_entries.async_forward_entry_setups.called

        # Get the entry's data in hass.data
        entry_data = mock_hass.data[DOMAIN][mock_config_entry.entry_id]
        assert "coordinator" in entry_data
        assert "devices" in entry_data

        from custom_components.renogy_ha.sensor import (
            async_setup_entry as sensor_setup_entry,
        )

        # Call the real sensor setup entry function
        await sensor_setup_entry(mock_hass, mock_config_entry, MagicMock())

        # Check that BLE polling was started
        assert mock_coordinator.start_polling.called

        # Simulate the device discovery by adding a mock device to the coordinator
        from custom_components.renogy_ha.sensor import RenogyBLESensor

        # Set up device registry mock
        device_registry = MagicMock()
        with patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=device_registry,
        ):

            # Create a mock coordinator for sensor testing
            test_coordinator = MagicMock()
            test_coordinator.devices = {mock_renogy_device.address: mock_renogy_device}

            # Add the coordinator to hass.data for the entry
            mock_hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"] = (
                test_coordinator
            )
            mock_hass.data[DOMAIN][mock_config_entry.entry_id]["devices"] = [
                mock_renogy_device
            ]

            # Manually create sensor entities for testing
            sensors = []
            categories = ["Battery", "PV", "Load", "Controller"]

            for category in categories:
                sensor = RenogyBLESensor(
                    test_coordinator,
                    mock_renogy_device,
                    MagicMock(
                        key="test_key",
                        name="Test Sensor",
                        value_fn=lambda data: data.get("battery_voltage"),
                    ),
                    category=category,
                )
                sensors.append(sensor)

            # Check that all sensors were created with the right categories
            sensor_categories = {"Battery": 0, "PV": 0, "Load": 0, "Controller": 0}

            for sensor in sensors:
                assert isinstance(sensor, RenogyBLESensor)
                if sensor._category in sensor_categories:
                    sensor_categories[sensor._category] += 1

            # Verify we have sensors in each category
            for category, count in sensor_categories.items():
                assert count > 0, f"No sensors found in {category} category"

            # Check device info for each sensor
            for sensor in sensors:
                device_info = sensor.device_info

                # Verify device info attributes
                assert (DOMAIN, mock_renogy_device.address) in device_info[
                    "identifiers"
                ]
                assert "name" in device_info
                assert device_info["manufacturer"] == "Renogy"
                # Check that model is properly set from parsed data when available
                if (
                    mock_renogy_device.parsed_data
                    and "model" in mock_renogy_device.parsed_data
                ):
                    assert (
                        device_info["model"] == mock_renogy_device.parsed_data["model"]
                    )

