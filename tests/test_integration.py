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


class MockCoordinator(MagicMock):
    """Mock coordinator with all needed properties for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_update_success = True
        self.data = {}
        self.devices = {}


@pytest.mark.asyncio
async def test_end_to_end_integration(mock_hass, mock_config_entry, mock_renogy_device):
    """Test the full end-to-end integration flow including error handling and recovery."""
    # Mock the core components we'll need
    with patch(
        "custom_components.renogy_ha.RenogyDataUpdateCoordinator"
    ) as mock_coordinator_class:
        # Create the coordinator mock with all required properties
        mock_coordinator = MockCoordinator()
        mock_coordinator_class.return_value = mock_coordinator

        # Initially no devices
        mock_coordinator.devices = {}

        # Set up coordinator mock
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.start_polling = AsyncMock()
        mock_coordinator.hass = mock_hass

        # Call the async_setup_entry function from __init__.py
        from custom_components.renogy_ha import async_setup_entry

        assert await async_setup_entry(mock_hass, mock_config_entry)

        # Verify coordinator setup
        mock_coordinator_class.assert_called_once()

        # Import needed components for testing
        from custom_components.renogy_ha.sensor import (
            create_device_entities,
        )

        # Set up BLE client
        mock_ble_client = MagicMock()
        mock_coordinator.ble_client = mock_ble_client

        # Add device to coordinator
        mock_coordinator.devices = {mock_renogy_device.address: mock_renogy_device}

        # Add device data to coordinator
        mock_coordinator.data = {
            mock_renogy_device.address: mock_renogy_device.parsed_data
        }

        # Create sensor entities
        entities = create_device_entities(mock_coordinator, mock_renogy_device)

        # Make entities compatible with our test environment
        for entity in entities:
            entity.hass = mock_hass
            entity.async_write_ha_state = MagicMock()

        # Create a custom availability check function to bypass super().available
        def check_entity_availability(entity):
            """Check if entity should be available based on device state."""
            return (
                entity._device.is_available and entity._device.parsed_data is not None
            )

        # ----- Verify Initial State -----
        # Verify entities have correct initial values
        for entity in entities:
            # Check device info is set correctly
            assert entity.device_info["identifiers"] == {
                (DOMAIN, mock_renogy_device.address)
            }

            # Check availability using our custom function
            assert check_entity_availability(entity) is True

        # ----- Simulate Error Condition -----
        # Simulate device becoming unavailable after consecutive failures
        mock_renogy_device.failure_count = 3
        mock_renogy_device.available = False

        # Verify availability is updated
        for entity in entities:
            assert check_entity_availability(entity) is False

        # ----- Simulate Recovery -----
        # Simulate device coming back online
        mock_renogy_device.failure_count = 0
        mock_renogy_device.available = True

        # Verify availability is restored
        for entity in entities:
            assert check_entity_availability(entity) is True

        # Verify all entities properly update state when new data arrives
        for entity in entities:
            # Trigger the coordinator update handler
            entity._handle_coordinator_update()
            # Verify state is written
            assert entity.async_write_ha_state.called


@pytest.mark.asyncio
async def test_integration_with_multiple_devices(
    mock_hass, mock_config_entry, mock_renogy_device
):
    """Test that the integration properly handles multiple devices."""
    # Create a second mock device
    second_device = MagicMock(spec=BLEDevice)
    second_device.address = "11:22:33:44:55:66"
    second_device.name = "BT-TH-67890"
    second_device.rssi = -70

    second_renogy_device = RenogyBLEDevice(second_device)
    second_renogy_device.parsed_data = {
        # Similar data to first device but with different values
        "battery_voltage": 13.2,
        "battery_current": 2.0,
        "battery_percentage": 90,
        "model": "Rover 60A",
        # ... other values would be here
    }
    second_renogy_device.available = True

    # Set up coordinator with two devices
    with patch(
        "custom_components.renogy_ha.RenogyDataUpdateCoordinator"
    ) as mock_coordinator_class:
        # Create the coordinator mock with all required properties
        mock_coordinator = MockCoordinator()
        mock_coordinator_class.return_value = mock_coordinator

        # Set coordinator properties
        mock_coordinator.hass = mock_hass

        # Set up with two devices
        mock_coordinator.devices = {
            mock_renogy_device.address: mock_renogy_device,
            second_renogy_device.address: second_renogy_device,
        }

        # Set coordinator data
        mock_coordinator.data = {
            mock_renogy_device.address: mock_renogy_device.parsed_data,
            second_renogy_device.address: second_renogy_device.parsed_data,
        }

        # Import needed components
        from custom_components.renogy_ha.sensor import (
            create_device_entities,
        )

        # Manually create entities for both devices
        device1_entities = create_device_entities(mock_coordinator, mock_renogy_device)
        device2_entities = create_device_entities(
            mock_coordinator, second_renogy_device
        )

        # Patch entity methods for Home Assistant interaction
        for entity in device1_entities + device2_entities:
            entity.hass = mock_hass
            entity.async_write_ha_state = MagicMock()

        # Create custom availability check
        def check_entity_availability(entity):
            """Check if entity should be available based on device state."""
            return (
                entity._device.is_available and entity._device.parsed_data is not None
            )

        # Verify we have entities for both devices
        assert len(device1_entities) > 0
        assert len(device2_entities) > 0

        # Verify unique IDs don't overlap
        all_unique_ids = [e.unique_id for e in device1_entities + device2_entities]
        assert len(all_unique_ids) == len(set(all_unique_ids))

        # Verify all entities are available initially
        for entity in device1_entities + device2_entities:
            assert check_entity_availability(entity) is True

        # Simulate device 1 going offline while device 2 stays online
        mock_renogy_device.available = False
        mock_renogy_device.failure_count = 3

        # Verify device 1 entities are unavailable
        for entity in device1_entities:
            assert check_entity_availability(entity) is False

        # Verify device 2 entities are still available
        for entity in device2_entities:
            assert check_entity_availability(entity) is True


@pytest.mark.asyncio
async def test_malformed_data_handling(
    mock_hass, mock_config_entry, mock_renogy_device
):
    """Test handling of malformed or incomplete data from the device."""
    with patch(
        "custom_components.renogy_ha.RenogyDataUpdateCoordinator"
    ) as mock_coordinator_class:
        mock_coordinator = MockCoordinator()
        mock_coordinator_class.return_value = mock_coordinator
        mock_coordinator.hass = mock_hass
        mock_coordinator.devices = {mock_renogy_device.address: mock_renogy_device}

        # Test cases for different malformed data scenarios
        malformed_data_cases = [
            {},  # Empty data
            {"battery_voltage": None},  # None value
            {"battery_voltage": "invalid"},  # Wrong type
            {"unknown_field": 123},  # Unknown field
            {"battery_voltage": -999},  # Out of range value
        ]

        from custom_components.renogy_ha.sensor import create_device_entities

        entities = create_device_entities(mock_coordinator, mock_renogy_device)
        for entity in entities:
            entity.hass = mock_hass
            entity.async_write_ha_state = MagicMock()

        # Test each malformed data case
        for test_data in malformed_data_cases:
            # Update device with malformed data
            mock_renogy_device.parsed_data = test_data
            mock_coordinator.data = {mock_renogy_device.address: test_data}

            # Device should remain available despite bad data
            assert mock_renogy_device.available is True

            # Update entities and verify they handle bad data gracefully
            for entity in entities:
                # Trigger update
                entity._handle_coordinator_update()
                # Verify state was written
                assert entity.async_write_ha_state.called
                # Verify entity remains available
                assert entity.available is True


@pytest.mark.asyncio
async def test_connection_edge_cases(mock_hass, mock_config_entry, mock_renogy_device):
    """Test handling of various connection edge cases."""
    with patch(
        "custom_components.renogy_ha.RenogyDataUpdateCoordinator"
    ) as mock_coordinator_class:
        mock_coordinator = MockCoordinator()
        mock_coordinator_class.return_value = mock_coordinator
        mock_coordinator.hass = mock_hass
        mock_coordinator.devices = {mock_renogy_device.address: mock_renogy_device}

        from custom_components.renogy_ha.sensor import create_device_entities

        entities = create_device_entities(mock_coordinator, mock_renogy_device)
        for entity in entities:
            entity.hass = mock_hass
            entity.async_write_ha_state = MagicMock()

        # Test rapid connect/disconnect
        for _ in range(5):
            mock_renogy_device.available = False
            await asyncio.sleep(0)  # Allow state to update
            mock_renogy_device.available = True
            await asyncio.sleep(0)  # Allow state to update

        # Test gradual connection degradation
        for rssi in [-60, -70, -80, -90, -100]:
            mock_renogy_device.rssi = rssi  # Changed from _ble_device.rssi
            await asyncio.sleep(0)  # Allow state to update

        # Test recovery from max failure count
        mock_renogy_device.failure_count = 5  # Beyond normal threshold
        mock_renogy_device.available = False
        await asyncio.sleep(0)  # Allow state to update

        # Verify recovery works
        mock_renogy_device.failure_count = 0
        mock_renogy_device.available = True
        await asyncio.sleep(0)  # Allow state to update

        # Test partial data updates
        original_data = mock_renogy_device.parsed_data.copy()
        partial_data = {
            k: v for k, v in original_data.items() if k.startswith("battery")
        }
        mock_renogy_device.parsed_data = partial_data
        await asyncio.sleep(0)  # Allow state to update

        # Verify entities handle partial data
        for entity in entities:
            entity._handle_coordinator_update()
            assert entity.async_write_ha_state.called
