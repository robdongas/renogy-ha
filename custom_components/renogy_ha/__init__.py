"""Renogy BLE integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

import async_timeout
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
            # Use HA coordinator's update interval for proper integration with HA's scheduler
            update_interval=timedelta(seconds=scan_interval),
        )
        self.ble_client = RenogyBLEClient(
            scan_interval=scan_interval,
            data_callback=self._handle_device_data,
        )
        self.devices: Dict[str, RenogyBLEDevice] = {}
        self.scan_interval = scan_interval

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from BLE devices.

        This method is called by DataUpdateCoordinator on the update interval.
        Instead of directly fetching data here, we delegate to the BLE client's
        polling mechanism, but occasionally trigger a scan to discover new devices.
        """
        try:
            async with async_timeout.timeout(self.scan_interval * 0.8):
                # Initiate a scan for devices if we don't have any yet or periodically
                if not self.devices or self.update_interval.total_seconds() >= 60:
                    LOGGER.debug("Scanning for new Renogy BLE devices")
                    devices = await self.ble_client.scan_for_devices()
                    for device in devices:
                        if device.address not in self.devices:
                            LOGGER.info(
                                f"Discovered new Renogy device: {device.name} ({device.address})"
                            )
                            self.devices[device.address] = device

                # Return the current data - actual updates happen via the callback
                return {
                    addr: device.parsed_data
                    for addr, device in self.devices.items()
                    if device.parsed_data
                }
        except Exception as err:
            LOGGER.error(f"Error fetching Renogy BLE data: {err}")
            # Return last known good data
            return {
                addr: device.parsed_data
                for addr, device in self.devices.items()
                if device.parsed_data
            }

    async def start_polling(self) -> None:
        """Start the BLE polling."""
        LOGGER.info(
            "Starting Renogy BLE polling with scan interval of %s seconds",
            self.scan_interval,
        )
        await self.ble_client.start_polling()

    def _handle_device_data(self, device: RenogyBLEDevice) -> None:
        """Handle updated data from a device."""
        LOGGER.debug(f"Received update from device: {device.name} ({device.address})")

        # Register or update the device in our device registry
        self.devices[device.address] = device

        # Find all entries in hass.data[DOMAIN] that could contain this device
        for entry_id, entry_data in self.hass.data[DOMAIN].items():
            devices_list = entry_data.get("devices", [])

            # Check if device is already in list by address
            device_addresses = [d.address for d in devices_list]
            if device.address not in device_addresses:
                LOGGER.debug(f"Registering device {device.name} with Home Assistant")
                devices_list.append(device)

        # Trigger an update for all entities using this coordinator
        LOGGER.debug(f"Updating entities for device {device.name}")
        self.async_set_updated_data(
            {addr: d.parsed_data for addr, d in self.devices.items() if d.parsed_data}
        )

        # Mark device as successfully updated
        LOGGER.debug(f"Device {device.name} update processed")
