"""Config flow for Renogy BLE integration."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
)
from homeassistant.const import CONF_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResult

from .ble import RenogyActiveBluetoothCoordinator
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    RENOGY_BT_PREFIX,
    SUPPORTED_MODELS,
)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Renogy BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._discovered_device: BluetoothServiceInfoBleak | None = None
        self._coordinator: RenogyActiveBluetoothCoordinator | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        # Check if this is a Renogy device based on the name
        if not discovery_info.name or not discovery_info.name.startswith(
            RENOGY_BT_PREFIX
        ):
            return self.async_abort(reason="not_supported_device")

        LOGGER.info(
            f"Bluetooth auto-discovery for Renogy device: {discovery_info.name} ({discovery_info.address})"
        )

        # Set unique ID based on device address
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        # Store the discovered device for later
        self._discovered_device = discovery_info

        # Set title to user-readable name
        self.context["title_placeholders"] = {
            "name": discovery_info.name,
            "address": discovery_info.address,
        }

        # Proceed to configuration options
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device or configure options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if self._discovered_device:
                # Coming from bluetooth discovery with device already selected
                address = self._discovered_device.address
                user_input[CONF_ADDRESS] = address

                # Before creating the entry, check if the device model is supported
                if await self._verify_supported_model(address):
                    # Create a config entry
                    return self.async_create_entry(
                        title=self._discovered_device.name,
                        data=user_input,
                    )
                else:
                    errors["base"] = "unsupported_model"

            elif CONF_ADDRESS in user_input:
                # Manual device selection
                address = user_input[CONF_ADDRESS]
                discovery_info = self._discovered_devices[address]

                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                # Before creating the entry, check if the device model is supported
                if await self._verify_supported_model(address):
                    return self.async_create_entry(
                        title=discovery_info.name,
                        data=user_input,
                    )
                else:
                    errors["base"] = "unsupported_model"

        # If we have a discovered device from bluetooth auto-discovery,
        # just show config options (scan interval, etc)
        if self._discovered_device:
            return self.async_show_form(
                step_id="user",
                data_schema=CONFIG_SCHEMA,
                description_placeholders={
                    "device_name": self._discovered_device.name,
                    "default_interval": DEFAULT_SCAN_INTERVAL,
                },
                errors=errors,
            )

        # Otherwise, scan for available devices to let the user pick one
        await self._async_discover_devices()

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        # Show form to select a discovered device
        address_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(
                    {
                        address: f"{info.name} ({address})"
                        for address, info in self._discovered_devices.items()
                    }
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=address_schema,
            errors=errors,
        )

    async def _verify_supported_model(self, address: str) -> bool:
        """Verify that the device model is supported."""
        LOGGER.info(f"Verifying model support for device at {address}")

        # Create a temporary coordinator to communicate with the device
        self._coordinator = RenogyActiveBluetoothCoordinator(
            hass=self.hass,
            logger=LOGGER,
            address=address,
            scan_interval=DEFAULT_SCAN_INTERVAL,
        )

        # Set up the coordinator and request a refresh to get device data
        unsub = self._coordinator.async_start()

        try:
            # Perform an initial refresh to get data
            await self._coordinator.async_request_refresh()

            # Wait for a moment to get data (max 15 seconds)
            for _ in range(15):
                # Check if we have model data
                if self._coordinator.data and "model" in self._coordinator.data:
                    model = self._coordinator.data["model"]
                    LOGGER.info(f"Detected device model: {model}")

                    # Check if the model is in our supported list
                    if model in SUPPORTED_MODELS:
                        LOGGER.info(f"Model {model} is supported")
                        return True
                    else:
                        LOGGER.warning(
                            f"Model {model} is not in the supported models list: {SUPPORTED_MODELS}"
                        )
                        return False

                # If we don't have data yet, wait a second and try again
                await asyncio.sleep(1)

            # If we got here, we couldn't determine the model - assume not supported
            LOGGER.warning("Could not determine device model within timeout period")
            return False

        finally:
            # Always clean up the coordinator
            unsub()
            if self._coordinator:
                self._coordinator.async_stop()

    async def _async_discover_devices(self) -> None:
        """Discover Bluetooth devices."""
        LOGGER.info("Scanning for Renogy BLE devices")

        self._discovered_devices = {}

        for discovery_info in bluetooth.async_discovered_service_info(self.hass):
            # Skip devices that don't match our pattern
            if not discovery_info.name or not discovery_info.name.startswith(
                RENOGY_BT_PREFIX
            ):
                continue

            # Skip devices that are already configured
            address = discovery_info.address
            if address in self._async_current_ids():
                continue

            # Add to list of discovered devices
            self._discovered_devices[address] = discovery_info
            LOGGER.info(f"Found Renogy device: {discovery_info.name} ({address})")

        LOGGER.info(
            f"Found {len(self._discovered_devices)} unconfigured Renogy devices"
        )
