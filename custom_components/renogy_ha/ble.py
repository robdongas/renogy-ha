"""BLE communication module for Renogy devices."""

import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable

import bleak
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice

from .const import (
    LOGGER,
    RENOGY_BT_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
)

class RenogyBLEDevice:
    """Representation of a Renogy BLE device."""

    def __init__(self, ble_device: BLEDevice):
        """Initialize the Renogy BLE device."""
        self.ble_device = ble_device
        self.address = ble_device.address
        self.name = ble_device.name or "Unknown Renogy Device"
        self.rssi = ble_device.rssi
        self.last_seen = datetime.now()
        # To store last received data
        self.data: Optional[Dict[str, Any]] = None
        # Track consecutive failures
        self.failure_count = 0
        # Maximum allowed failures before marking device unavailable
        self.max_failures = 3
        # Device availability tracking
        self.available = True

    @property
    def is_available(self) -> bool:
        """Return True if device is available."""
        return self.available and self.failure_count < self.max_failures

    def update_availability(self, success: bool) -> None:
        """Update the availability based on success/failure of communication."""
        if success:
            self.failure_count = 0
            if not self.available:
                LOGGER.info("Device %s is now available", self.name)
                self.available = True
        else:
            self.failure_count += 1
            if self.failure_count >= self.max_failures and self.available:
                LOGGER.warning(
                    "Device %s marked unavailable after %s consecutive failures",
                    self.name, self.max_failures
                )
                self.available = False


class RenogyBLEClient:
    """Client to handle BLE communication with Renogy devices."""

    def __init__(
        self,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        data_callback: Optional[Callable[[RenogyBLEDevice], None]] = None,
    ):
        """Initialize the BLE client."""
        self.discovered_devices: Dict[str, RenogyBLEDevice] = {}
        self._scanner = BleakScanner()
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self.scan_interval = max(MIN_SCAN_INTERVAL, min(scan_interval, MAX_SCAN_INTERVAL))
        self.data_callback = data_callback

    def is_renogy_device(self, device: BLEDevice) -> bool:
        """Check if a BLE device is a Renogy device by examining its name."""
        if device.name is None:
            return False
        return device.name.startswith(RENOGY_BT_PREFIX)

    async def scan_for_devices(self) -> List[RenogyBLEDevice]:
        """Scan for Renogy BLE devices and return a list of discovered devices."""
        LOGGER.debug("Starting BLE scan for Renogy devices")
        
        try:
            devices = await self._scanner.discover()
            renogy_devices = []
            
            for device in devices:
                if self.is_renogy_device(device):
                    LOGGER.debug("Found Renogy device: %s (%s)", device.name, device.address)
                    
                    # Either get existing device or create new one
                    if device.address in self.discovered_devices:
                        renogy_device = self.discovered_devices[device.address]
                        renogy_device.ble_device = device  # Update with latest device info
                        renogy_device.rssi = device.rssi
                        renogy_device.last_seen = datetime.now()
                    else:
                        renogy_device = RenogyBLEDevice(device)
                        self.discovered_devices[device.address] = renogy_device
                    
                    renogy_devices.append(renogy_device)
            
            LOGGER.debug("Found %s Renogy devices", len(renogy_devices))
            return renogy_devices
        except Exception as e:
            LOGGER.error("Error scanning for Renogy devices: %s", str(e))
            return []

    async def start_polling(self) -> None:
        """Start the BLE polling loop."""
        if self._running:
            LOGGER.warning("Polling already running, not starting again")
            return
        
        LOGGER.info("Starting Renogy BLE polling with interval %s seconds", self.scan_interval)
        self._running = True
        self._scan_task = asyncio.create_task(self._polling_loop())

    async def stop_polling(self) -> None:
        """Stop the BLE polling loop."""
        if not self._running:
            return
        
        LOGGER.info("Stopping Renogy BLE polling")
        self._running = False
        if self._scan_task is not None:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

    async def _polling_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                devices = await self.scan_for_devices()
                
                # Process each discovered device
                for device in devices:
                    # Here we would typically connect to the device and get its data
                    # This will be expanded in the next implementation phase
                    # For now, we just log and notify via callback if it exists
                    LOGGER.debug("Processed device %s", device.name)
                    
                    if self.data_callback:
                        try:
                            self.data_callback(device)
                        except Exception as e:
                            LOGGER.error("Error in data callback: %s", str(e))
            
            except Exception as e:
                LOGGER.error("Error in polling loop: %s", str(e))
            
            # Wait for the next scan interval
            await asyncio.sleep(self.scan_interval)