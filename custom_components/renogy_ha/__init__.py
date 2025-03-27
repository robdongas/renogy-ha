"""Renogy BLE integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
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
    device_address = entry.data.get(CONF_ADDRESS)

    if not device_address:
        LOGGER.error("No device address provided in config entry")
        return False

    # Create a coordinator for this entry
    coordinator = RenogyDataUpdateCoordinator(hass, scan_interval, device_address)

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

    def __init__(
        self, hass: HomeAssistant, scan_interval: int, device_address: str
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            # Use HA coordinator's update interval for proper integration with HA's scheduler
            update_interval=timedelta(seconds=scan_interval),
        )
        # Initialize BLE client with the Home Assistant instance and specific device address
        self.ble_client = RenogyBLEClient(
            scan_interval=scan_interval,
            data_callback=self._handle_device_data,
            hass=hass,  # Pass the hass instance to use HA bluetooth APIs
            device_address=device_address,  # Only track the specific device
        )
        self.devices: Dict[str, RenogyBLEDevice] = {}
        self.scan_interval = scan_interval
        self.device_address = device_address

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from BLE devices.

        This method is called by DataUpdateCoordinator on the update interval.
        It only processes the specific device configured for this entry.
        """
        try:
            async with async_timeout.timeout(self.scan_interval * 0.8):
                # We're only interested in the specific device for this entry
                LOGGER.debug(f"Checking for Renogy BLE device {self.device_address}")
                device = await self.ble_client.get_device_by_address(
                    self.device_address
                )

                if device:
                    if device.address not in self.devices:
                        LOGGER.info(
                            f"Tracking Renogy device: {device.name} ({device.address})"
                        )
                        self.devices[device.address] = device

                    # Process the device data
                    await self.ble_client._process_device(device)

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
            f"Starting Renogy BLE polling for device {self.device_address} with scan interval of {self.scan_interval} seconds"
        )
        await self.ble_client.start_polling()

    def _handle_device_data(self, device: RenogyBLEDevice) -> None:
        """Handle updated data from a device."""
        # Only process data for our specific device
        if device.address != self.device_address:
            LOGGER.debug(
                f"Ignoring update from non-tracked device: {device.name} ({device.address})"
            )
            return

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
