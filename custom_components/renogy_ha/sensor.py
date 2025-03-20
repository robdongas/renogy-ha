"""Support for Renogy BLE sensors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .ble import RenogyBLEDevice
from .const import ATTR_MANUFACTURER, ATTR_MODEL, DOMAIN, LOGGER

# Registry of sensor keys
KEY_BATTERY_VOLTAGE = "battery_voltage"
KEY_BATTERY_CURRENT = "battery_current"
KEY_BATTERY_PERCENTAGE = "battery_percentage"
KEY_BATTERY_TEMPERATURE = "battery_temperature"
KEY_BATTERY_TYPE = "battery_type"
KEY_CHARGING_AMP_HOURS_TODAY = "charging_amp_hours_today"
KEY_DISCHARGING_AMP_HOURS_TODAY = "discharging_amp_hours_today"
KEY_CHARGING_STATUS = "charging_status"

KEY_PV_VOLTAGE = "pv_voltage"
KEY_PV_CURRENT = "pv_current"
KEY_PV_POWER = "pv_power"
KEY_MAX_CHARGING_POWER_TODAY = "max_charging_power_today"
KEY_POWER_GENERATION_TODAY = "power_generation_today"
KEY_POWER_GENERATION_TOTAL = "power_generation_total"

KEY_LOAD_VOLTAGE = "load_voltage"
KEY_LOAD_CURRENT = "load_current"
KEY_LOAD_POWER = "load_power"
KEY_LOAD_STATUS = "load_status"
KEY_POWER_CONSUMPTION_TODAY = "power_consumption_today"

KEY_CONTROLLER_TEMPERATURE = "controller_temperature"
KEY_DEVICE_ID = "device_id"
KEY_MODEL = "model"
KEY_MAX_DISCHARGING_POWER_TODAY = "max_discharging_power_today"
KEY_FIRMWARE_VERSION = "firmware_version"

# Battery type text values mapping
BATTERY_TYPES = {0: "open", 1: "sealed", 2: "gel", 3: "lithium", 4: "custom"}

# Charging status text values mapping
CHARGING_STATUSES = {
    0: "deactivated",
    1: "activated",
    2: "mppt",
    3: "equalizing",
    4: "boost",
    5: "floating",
    6: "current limiting",
}

# Load status text values mapping
LOAD_STATUSES = {0: "off", 1: "on"}


@dataclass
class RenogyBLESensorDescription(SensorEntityDescription):
    """Describes a Renogy BLE sensor."""

    # Function to extract value from the device's parsed data
    value_fn: Optional[Callable[[Dict[str, Any]], Any]] = None


BATTERY_SENSORS: tuple[RenogyBLESensorDescription, ...] = (
    RenogyBLESensorDescription(
        key=KEY_BATTERY_VOLTAGE,
        name="Battery Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_BATTERY_VOLTAGE),
    ),
    RenogyBLESensorDescription(
        key=KEY_BATTERY_CURRENT,
        name="Battery Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_BATTERY_CURRENT),
    ),
    RenogyBLESensorDescription(
        key=KEY_BATTERY_PERCENTAGE,
        name="Battery Percentage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_BATTERY_PERCENTAGE),
    ),
    RenogyBLESensorDescription(
        key=KEY_BATTERY_TEMPERATURE,
        name="Battery Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_BATTERY_TEMPERATURE),
    ),
    RenogyBLESensorDescription(
        key=KEY_BATTERY_TYPE,
        name="Battery Type",
        device_class=None,
        value_fn=lambda data: BATTERY_TYPES.get(data.get(KEY_BATTERY_TYPE), "unknown"),
    ),
    RenogyBLESensorDescription(
        key=KEY_CHARGING_AMP_HOURS_TODAY,
        name="Charging Amp Hours Today",
        native_unit_of_measurement="Ah",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get(KEY_CHARGING_AMP_HOURS_TODAY),
    ),
    RenogyBLESensorDescription(
        key=KEY_DISCHARGING_AMP_HOURS_TODAY,
        name="Discharging Amp Hours Today",
        native_unit_of_measurement="Ah",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get(KEY_DISCHARGING_AMP_HOURS_TODAY),
    ),
    RenogyBLESensorDescription(
        key=KEY_CHARGING_STATUS,
        name="Charging Status",
        device_class=None,
        value_fn=lambda data: CHARGING_STATUSES.get(
            data.get(KEY_CHARGING_STATUS), "unknown"
        ),
    ),
)

PV_SENSORS: tuple[RenogyBLESensorDescription, ...] = (
    RenogyBLESensorDescription(
        key=KEY_PV_VOLTAGE,
        name="PV Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_PV_VOLTAGE),
    ),
    RenogyBLESensorDescription(
        key=KEY_PV_CURRENT,
        name="PV Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_PV_CURRENT),
    ),
    RenogyBLESensorDescription(
        key=KEY_PV_POWER,
        name="PV Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_PV_POWER),
    ),
    RenogyBLESensorDescription(
        key=KEY_MAX_CHARGING_POWER_TODAY,
        name="Max Charging Power Today",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_MAX_CHARGING_POWER_TODAY),
    ),
    RenogyBLESensorDescription(
        key=KEY_POWER_GENERATION_TODAY,
        name="Power Generation Today",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get(KEY_POWER_GENERATION_TODAY),
    ),
    RenogyBLESensorDescription(
        key=KEY_POWER_GENERATION_TOTAL,
        name="Power Generation Total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get(KEY_POWER_GENERATION_TOTAL),
    ),
)

LOAD_SENSORS: tuple[RenogyBLESensorDescription, ...] = (
    RenogyBLESensorDescription(
        key=KEY_LOAD_VOLTAGE,
        name="Load Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_LOAD_VOLTAGE),
    ),
    RenogyBLESensorDescription(
        key=KEY_LOAD_CURRENT,
        name="Load Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_LOAD_CURRENT),
    ),
    RenogyBLESensorDescription(
        key=KEY_LOAD_POWER,
        name="Load Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_LOAD_POWER),
    ),
    RenogyBLESensorDescription(
        key=KEY_LOAD_STATUS,
        name="Load Status",
        device_class=None,
        value_fn=lambda data: LOAD_STATUSES.get(data.get(KEY_LOAD_STATUS), "unknown"),
    ),
    RenogyBLESensorDescription(
        key=KEY_POWER_CONSUMPTION_TODAY,
        name="Power Consumption Today",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get(KEY_POWER_CONSUMPTION_TODAY),
    ),
)

CONTROLLER_SENSORS: tuple[RenogyBLESensorDescription, ...] = (
    RenogyBLESensorDescription(
        key=KEY_CONTROLLER_TEMPERATURE,
        name="Controller Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_CONTROLLER_TEMPERATURE),
    ),
    RenogyBLESensorDescription(
        key=KEY_DEVICE_ID,
        name="Device ID",
        device_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get(KEY_DEVICE_ID),
    ),
    RenogyBLESensorDescription(
        key=KEY_MODEL,
        name="Model",
        device_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get(KEY_MODEL),
    ),
    RenogyBLESensorDescription(
        key=KEY_FIRMWARE_VERSION,
        name="Firmware Version",
        device_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get(KEY_FIRMWARE_VERSION),
    ),
    RenogyBLESensorDescription(
        key=KEY_MAX_DISCHARGING_POWER_TODAY,
        name="Max Discharging Power Today",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(KEY_MAX_DISCHARGING_POWER_TODAY),
    ),
)

# All sensors combined
ALL_SENSORS = BATTERY_SENSORS + PV_SENSORS + LOAD_SENSORS + CONTROLLER_SENSORS


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Renogy BLE sensors."""
    LOGGER.debug("Setting up Renogy BLE sensors")

    renogy_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = renogy_data["coordinator"]

    # Start the BLE polling
    await coordinator.start_polling()

    # Entity tracking to avoid duplicates
    entity_registry = set()

    @callback
    def device_discovered_callback(device: RenogyBLEDevice) -> None:
        """Create entities for a newly discovered device."""
        if not device or not device.is_available:
            return

        # Create entities for this device if not already done
        new_entities = []
        device_id = f"{device.address}"

        if device_id in entity_registry:
            # Already set up this device
            return

        LOGGER.info(
            f"Creating entities for newly discovered device: {device.name} ({device.address})"
        )
        entity_registry.add(device_id)

        # Create all entities for this device
        device_entities = create_device_entities(coordinator, device)
        new_entities.extend(device_entities)

        # Register device in hass.data
        if device not in renogy_data["devices"]:
            LOGGER.debug(f"Adding device {device.name} to registry")
            renogy_data["devices"].append(device)

        # Add entities to Home Assistant
        if new_entities:
            LOGGER.debug(
                f"Adding {len(new_entities)} entities for device {device.name}"
            )
            async_add_entities(new_entities)

    # Set up callback for future device discoveries
    async def setup_discovered_devices() -> None:
        """Set up sensors for already discovered devices and register callback for new ones."""
        # Create entities for already discovered devices
        initial_entities = []

        # Add entities for devices discovered so far
        for device_address, device in coordinator.devices.items():
            device_id = f"{device.address}"

            if device_id not in entity_registry:
                LOGGER.info(
                    f"Setting up initial device: {device.name} ({device.address})"
                )
                entity_registry.add(device_id)

                # Create entities for this device
                device_entities = create_device_entities(coordinator, device)
                initial_entities.extend(device_entities)

                # Register device in hass.data
                if device not in renogy_data["devices"]:
                    renogy_data["devices"].append(device)

        # Add initial entities
        if initial_entities:
            LOGGER.info(f"Adding {len(initial_entities)} initial entities")
            async_add_entities(initial_entities)

        # Register for future device discoveries
        coordinator.ble_client.data_callback = device_discovered_callback

    await setup_discovered_devices()


def create_device_entities(
    coordinator: DataUpdateCoordinator, device: RenogyBLEDevice
) -> List[RenogyBLESensor]:
    """Create sensor entities for a device."""
    entities = []

    # Group sensors by category
    for category_name, sensor_list in {
        "Battery": BATTERY_SENSORS,
        "PV": PV_SENSORS,
        "Load": LOAD_SENSORS,
        "Controller": CONTROLLER_SENSORS,
    }.items():
        for description in sensor_list:
            sensor = RenogyBLESensor(coordinator, device, description, category_name)
            entities.append(sensor)

    LOGGER.debug(f"Created {len(entities)} entities for device {device.name}")
    return entities


class RenogyBLESensor(CoordinatorEntity, SensorEntity):
    """Representation of a Renogy BLE sensor."""

    entity_description: RenogyBLESensorDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device: RenogyBLEDevice,
        description: RenogyBLESensorDescription,
        category: str = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device = device
        self._category = category
        self._attr_unique_id = f"{device.address}_{description.key}"
        self._last_updated = None
        self._attr_name = f"{device.name} {description.name}"

        # Properly set up device_info for the device registry
        model = (
            device.parsed_data.get(KEY_MODEL, ATTR_MODEL)
            if device.parsed_data
            else ATTR_MODEL
        )
        firmware_version = (
            device.parsed_data.get(KEY_FIRMWARE_VERSION) if device.parsed_data else None
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            name=device.name,
            manufacturer=ATTR_MANUFACTURER,
            model=model,
            sw_version=firmware_version,
            hw_version=f"BLE Address: {device.address}",
        )

        # Set initial availability based on device status
        self._attr_available = device.is_available

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._last_updated = datetime.now()

        # Always update availability based on device status
        self._attr_available = self._device.is_available

        try:
            # Get the latest data for our device from the coordinator
            if self.coordinator.data and self._device.address in self.coordinator.data:
                device_data = self.coordinator.data[self._device.address]
                if device_data is not None:
                    LOGGER.debug(
                        f"Updated sensor {self.name} with new value from coordinator"
                    )
            # Always write state, even if no data, to ensure UI updates
            self.async_write_ha_state()
        except Exception as e:
            LOGGER.warning(f"Error updating sensor {self.name}: {e}")
            # Still write state to show the error condition
            self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the sensor's value."""
        try:
            if not self._device.parsed_data:
                return None

            if self.entity_description.value_fn:
                value = self.entity_description.value_fn(self._device.parsed_data)

                # Basic type validation based on device_class
                if value is not None:
                    if self.device_class in [
                        SensorDeviceClass.VOLTAGE,
                        SensorDeviceClass.CURRENT,
                        SensorDeviceClass.TEMPERATURE,
                        SensorDeviceClass.POWER,
                    ]:
                        try:
                            value = float(value)
                            # Basic range validation
                            if value < -1000 or value > 10000:
                                LOGGER.warning(
                                    f"Value {value} out of reasonable range for {self.name}"
                                )
                                return None
                        except (ValueError, TypeError):
                            LOGGER.warning(
                                f"Invalid numeric value for {self.name}: {value}"
                            )
                            return None

                return value
        except Exception as e:
            LOGGER.warning(f"Error getting native value for {self.name}: {e}")
        return None

    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
        # Check both the coordinator's and the device's availability
        return (
            super().available
            and self._device.is_available
            and self._device.parsed_data is not None
        )

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}
        if self._last_updated:
            attrs["last_updated"] = self._last_updated.isoformat()

        # Add the device's RSSI as attribute
        if hasattr(self._device, "rssi") and self._device.rssi is not None:
            attrs["rssi"] = self._device.rssi

        return attrs
