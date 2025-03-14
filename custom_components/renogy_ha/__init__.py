"""Renogy BLE integration for Home Assistant."""

from __future__ import annotations

from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .ble import RenogyBLEClient, RenogyBLEDevice
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
)

# List of platforms this integration supports
PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Renogy BLE from a config entry."""
    LOGGER.debug("Setting up Renogy BLE integration")

    # Get configuration from entry
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    # Create a coordinator for this entry
    coordinator = RenogyDataUpdateCoordinator(hass, scan_interval)

    # Store coordinator and devices in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "devices": [],  # Will be populated as devices are discovered
    }

    # Start the coordinator
    await coordinator.async_config_entry_first_refresh()

    # Forward entry setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Stop the BLE client
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        await coordinator.ble_client.stop_polling()

        # Remove entry from hass.data
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class RenogyDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Renogy BLE data."""

    def __init__(self, hass: HomeAssistant, scan_interval: int) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=None,  # We'll handle the update interval in the BLE client
        )
        self.ble_client = RenogyBLEClient(
            scan_interval=scan_interval,
            data_callback=self._handle_device_data,
        )
        self.devices: Dict[str, RenogyBLEDevice] = {}

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from BLE devices."""
        # This is called by the DataUpdateCoordinator, but we're using our own polling
        # mechanism in the BLE client, so we just return the current data.
        return {addr: device.parsed_data for addr, device in self.devices.items()}

    async def start_polling(self) -> None:
        """Start the BLE polling."""
        await self.ble_client.start_polling()

    def _handle_device_data(self, device: RenogyBLEDevice) -> None:
        """Handle updated data from a device."""
        # Register or update the device in our device registry
        self.devices[device.address] = device

        # Register the device in Home Assistant's device registry if not already registered
        if (
            device.address
            not in self.hass.data[DOMAIN][next(iter(self.hass.data[DOMAIN]))]["devices"]
        ):
            self.hass.data[DOMAIN][next(iter(self.hass.data[DOMAIN]))][
                "devices"
            ].append(device)

        # Schedule an update for any entities using this coordinator
        self.async_set_updated_data(self._async_update_data())
