# Renogy Rover BLE Integration for Home Assistant

This custom Home Assistant integration provides monitoring capabilities for Renogy devices via Bluetooth Low Energy (BLE) connection, specifically for devices with BT-1 and BT-2 modules.

## Currently Supported Devices

- Renogy Rover

(Initially only Renogy Rover is supported. More devices may be added in the future.)

## Features

- Automatic discovery of Renogy BLE devices
- Monitor battery status (voltage, current, temperature, charge state)
- Monitor solar panel (PV) performance metrics
- Monitor load status and statistics
- Monitor controller information
- All data exposed as Home Assistant sensors

## Prerequisites

- Home Assistant instance (version 2025.3 or newer)
- Renogy device with BT-1 or BT-2 Bluetooth module
- A compatible Bluetooth adapter on your Home Assistant host device

## Installation

This integration can be installed via HACS (Home Assistant Community Store).

1. Ensure you have [HACS](https://hacs.xyz/) installed
2. Add this repository to your HACS custom repositories
3. Search for "Renogy" in the HACS store and install it
4. Restart Home Assistant

## Usage

After installation, the integration should automatically discover any supported Renogy devices within Bluetooth range of your Home Assistant instance. You can then add these devices through the Home Assistant UI.

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.