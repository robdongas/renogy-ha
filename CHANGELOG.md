# CHANGELOG


## v0.2.3 (2025-04-08)

### Bug Fixes

- Try syncing version again
  ([`d6414fb`](https://github.com/IAmTheMitchell/renogy-ha/commit/d6414fbdf8e9de92c9db53f264d7a49916e217bf))

- Use version_variables for json version update
  ([`b95bdc7`](https://github.com/IAmTheMitchell/renogy-ha/commit/b95bdc764930e239d28e69a4edcb127b9f311fcd))


## v0.2.2 (2025-04-07)

### Bug Fixes

- Sync version in pyproject.toml and manifest.json
  ([`c673422`](https://github.com/IAmTheMitchell/renogy-ha/commit/c67342272f5e3ce166e2628587717abe6b68b530))


## v0.2.1 (2025-04-07)

### Bug Fixes

- Remove invalid HACS keys
  ([`944643d`](https://github.com/IAmTheMitchell/renogy-ha/commit/944643de382969438d735bf96c0ef8f52debe69a))

### Continuous Integration

- Add HACS validate.yaml
  ([`351f3dc`](https://github.com/IAmTheMitchell/renogy-ha/commit/351f3dc2ee1cc3e85b2990ac1c8d13e2d805f44a))

- Point to manifest.json for version
  ([`2480393`](https://github.com/IAmTheMitchell/renogy-ha/commit/2480393f8d4db0d2ffc9a4c39b541df5bc6b8e0a))


## v0.2.0 (2025-04-07)

### Bug Fixes

- Capitalize firmware type
  ([`072e610`](https://github.com/IAmTheMitchell/renogy-ha/commit/072e61078f347b9edafe8b8e2d7ba0540b88c349))

- Catch and log error during startup
  ([`06363b4`](https://github.com/IAmTheMitchell/renogy-ha/commit/06363b4fb61c179be0a15f2111f93dadb28c2327))

- Restrict to Python >=3.13 due to Home Assistant constraints
  ([`12e10cd`](https://github.com/IAmTheMitchell/renogy-ha/commit/12e10cd1e744293631ee2b7d210a320203cf9482))

- Update pyproject.toml to support Python >=3.10
  ([`3e74f25`](https://github.com/IAmTheMitchell/renogy-ha/commit/3e74f25956a10f15cd30501ebaaf7512e5438ce4))

- Update to use new renogy-ble parse signature
  ([`38db89a`](https://github.com/IAmTheMitchell/renogy-ha/commit/38db89a2da218d11f9201284e9af5cda8e4cf6ce))

- Use device_type as temporary model name
  ([`1ce2002`](https://github.com/IAmTheMitchell/renogy-ha/commit/1ce200258b1a691c9f945fb1c0706a13dff7ead7))

### Chores

- Automate test and release
  ([`c211c83`](https://github.com/IAmTheMitchell/renogy-ha/commit/c211c836de216bc9bcf3de8a55ad58939c20edc3))

### Features

- Prompt user for device type
  ([`9150126`](https://github.com/IAmTheMitchell/renogy-ha/commit/9150126137588ab59dc72a19fba4d6ea7994bd69))

- Update to latest renogy-ble library
  ([`50542ec`](https://github.com/IAmTheMitchell/renogy-ha/commit/50542ecbd3a615aaabf2c479bc4b6a1864c9c7fb))

### Refactoring

- Divy up commands by device type
  ([`7c7fed1`](https://github.com/IAmTheMitchell/renogy-ha/commit/7c7fed1fe18bbdb6cf7fff6c403510de4de33a8a))

- Dry up config schema
  ([`85e6d18`](https://github.com/IAmTheMitchell/renogy-ha/commit/85e6d1844d44a98d2f21f8dd20ead0246cd24c17))

- Dry up entity creation
  ([`8bbc216`](https://github.com/IAmTheMitchell/renogy-ha/commit/8bbc2163961dc98f98e69e82c45d3ea0809efc5b))

- Move config values to const.py
  ([`3f8ef75`](https://github.com/IAmTheMitchell/renogy-ha/commit/3f8ef75d8786612042e20f244cbe34705443a7a3))

- Remove unused constants
  ([`bcd5cd9`](https://github.com/IAmTheMitchell/renogy-ha/commit/bcd5cd977b730135990a003b16da6a9aff4412e9))

- Use Enum for device type
  ([`b846f19`](https://github.com/IAmTheMitchell/renogy-ha/commit/b846f19d1202c466747b9fe7cca1b25a91c72167))

- Use f strings formatting
  ([`7c874a9`](https://github.com/IAmTheMitchell/renogy-ha/commit/7c874a9521d65545f0bae7f2d581451edae22ea8))


## v0.1.7 (2025-03-21)


## v0.1.6 (2025-03-20)


## v0.1.5 (2025-03-19)


## v0.1.4 (2025-03-19)
