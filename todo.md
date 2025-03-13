# Renogy Rover BLE Integration Todo Checklist

This checklist outlines all the steps needed to implement the Renogy Rover BLE integration for Home Assistant. Follow each item carefully and check them off as you complete each task.

---

## 1. Project Setup & Structure
- [x] **Repository Initialization**
  - [x] Create the repository.
  - [x] Set up the directory structure:
    ```
    custom_components/
    └── renogy_ha/
        ├── __init__.py
        ├── hacs.json
        ├── config_flow.py   (if needed for UI configuration)
        ├── sensor.py
        ├── ble.py
        ├── const.py
        └── tests/
             ├── __init__.py
             └── test_ble.py
    ```
- [x] **Metadata and Licensing**
  - [x] Write a minimal `hacs.json` with name, version, documentation URL, and supported Home Assistant versions.
  - [x] Create a minimal README describing the integration's purpose and usage.
  - [x] Add the Apache License 2.0 file to the repository.
  - [X] Ensure all placeholder files (`__init__.py`, `config_flow.py`, etc.) are created.

---

## 2. BLE Communication Module
- [x] **Basic BLE Functionality**
  - [x] In `ble.py`, implement BLE scanning for Renogy Rover devices (BT-1 and BT-2 modules) using their unique Bluetooth identifiers.
  - [x] Implement a polling function with a default interval of 60 seconds, and make it configurable (range: 10–600 seconds).
  - [x] Add logging for the start and stop of the scanning process.
- [x] **Testing BLE Scanning**
  - [x] Create a test stub in `tests/test_ble.py` to mock BLE scanning.
  - [x] Ensure the test returns a dummy list of devices and validates the scanning function.

---

## 3. Data Parsing & Integration of `renogy-ble` Library
- [ ] **Parsing Raw Data**
  - [ ] In `ble.py`, integrate the `renogy-ble` library to parse raw Modbus data.
  - [ ] Read raw data from the discovered BLE devices.
  - [ ] Pass the raw data to the parsing library and retrieve structured data.
- [ ] **Data Scaling and Mapping**
  - [ ] Ensure numeric values are scaled correctly (e.g., battery voltage ×0.1, current ×0.01, etc.) based on the register map.
- [ ] **Unit Testing Parsing**
  - [ ] Write unit tests to supply sample raw data and validate that the parsed output matches expected sensor values.

---

## 4. Sensor Entity Mapping
- [ ] **Create Sensor Entities**
  - [ ] In `sensor.py`, create Home Assistant sensor classes for the following groups:
    - Battery
    - Solar Panel (PV)
    - Load
    - Controller Info
- [ ] **Attribute Configuration**
  - [ ] Assign proper attributes to each sensor (name, unit of measurement, device_class, state_class).
  - [ ] Map each sensor to its corresponding value from the parsed data.
- [ ] **Testing Sensor Mapping**
  - [ ] Write tests to confirm that, given sample parsed data, sensor entities are instantiated with correct values and metadata.

---

## 5. Device Discovery & Auto-Registration
- [ ] **Integration Initialization**
  - [ ] Modify `__init__.py` to start BLE polling at the configured interval.
- [ ] **Device Registration**
  - [ ] On device discovery, register/update the device in the Home Assistant device registry with attributes (manufacturer, model, firmware version, device ID).
- [ ] **Sensor Update Wiring**
  - [ ] Ensure that sensor entities are updated with the latest values from BLE polling.
- [ ] **Integration Testing**
  - [ ] Write tests that simulate device discovery.
  - [ ] Verify that the device is registered and sensors are created with correct attributes.

---

## 6. Error Handling and Availability Management
- [ ] **Failure Tracking**
  - [ ] Implement logic to track consecutive polling failures.
  - [ ] After 3 consecutive failures, mark the device/sensors as unavailable.
- [ ] **Recovery Logic**
  - [ ] Implement logic to mark the device/sensors as available once a successful poll is received.
- [ ] **Logging**
  - [ ] Log all communication errors and recovery events.
- [ ] **Testing Error Handling**
  - [ ] Write unit tests to simulate consecutive failures and ensure devices are marked unavailable.
  - [ ] Test recovery behavior when BLE communication is restored.

---

## 7. End-to-End Integration and Wiring
- [ ] **Wiring Components Together**
  - [ ] Integrate BLE communication, parsing, sensor entity creation, and error handling.
  - [ ] Create a main loop or scheduled task to trigger polling and sensor updates at the configured interval.
- [ ] **Full Cycle Testing**
  - [ ] Write comprehensive integration tests that simulate the full cycle:
    - Device discovery
    - Data parsing
    - Sensor updates
    - Error simulation and recovery
  - [ ] Ensure all entities are correctly updated and no orphaned code exists.

---

## 8. Documentation and Final Testing
- [ ] **Documentation Update**
  - [ ] Update the README with:
    - Installation instructions
    - Configuration details (polling interval, etc.)
    - Supported hardware list (Renogy Rover with BT-1/BT-2 and Bluetooth adapter)
    - Troubleshooting steps
- [ ] **Final Test Suite**
  - [ ] Write additional tests for edge cases (malformed data, unexpected disconnections).
  - [ ] Confirm that all unit and integration tests pass.
- [ ] **Code Review and Integration Checklist**
  - [ ] Perform a final review to ensure all components are integrated.
  - [ ] Verify adherence to Home Assistant integration best practices.
  - [ ] Finalize the integration for deployment via HACS.

---
