# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom component that syncs time and settings to LYWSD02 Bluetooth e-Ink clocks via HA's bluetooth integration (including ESPHome BLE proxies). Distributed via HACS.

There are no tests, no build system, and no linter configuration. The entire implementation is a single Python file.

## Architecture

The component registers one HA service (`lywsd02.set_time`) that:
1. Resolves the BLE device via HA's `bluetooth.async_ble_device_from_address`
2. Connects using `BleakClient` with a configurable timeout (default 60s)
3. Writes to two GATT characteristics:
   - `_UUID_TIME` (`EBE0CCB7-…`) — packed struct `(int timestamp, byte tz_offset)`, also reused for clock_mode writes
   - `_UUID_TEMO` (`EBE0CCBE-…`) — single byte for C/F temperature mode

`get_localized_timestamp()` converts wall-clock time to a local epoch by subtracting the UTC offset, since the device expects local time as an integer.

## Key Files

- `custom_components/lywsd02/__init__.py` — entire integration logic
- `custom_components/lywsd02/services.yaml` — service schema (mac, timestamp, tz_offset, temp_mode, clock_mode, timeout)
- `custom_components/lywsd02/manifest.json` — HA integration metadata; bump `version` here on each release

## Installation for Development

Copy (or symlink) `custom_components/lywsd02/` into your HA `config/custom_components/` directory, then add `lywsd02:` to `configuration.yaml` and restart HA.

## Versioning

Version is defined only in `manifest.json`. Update it before tagging a release.
