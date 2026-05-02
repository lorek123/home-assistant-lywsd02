from __future__ import annotations

import time
import struct
import logging

from datetime import datetime, timezone, timedelta

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from homeassistant.components import bluetooth

DOMAIN = "lywsd02"

_LOGGER = logging.getLogger(__name__)

_UUID_TIME = "EBE0CCB7-7A0A-4B0C-8A1A-6FF2997DA3A6"
_UUID_TEMO = "EBE0CCBE-7A0A-4B0C-8A1A-6FF2997DA3A6"


def get_localized_timestamp() -> tuple[int, int]:
    """Return (timestamp, tz_offset_hours) for the current local timezone.

    For partial-hour offsets (e.g. UTC+5:30), the sub-hour remainder is folded
    into the timestamp so the device always receives a whole-hour tz_offset.
    """
    now = time.time()
    utc = datetime.fromtimestamp(now, timezone.utc)
    local = datetime.fromtimestamp(now)
    diff = (local.replace(tzinfo=timezone.utc) - utc).total_seconds()
    diff_hours, diff_seconds = divmod(diff, 3600)
    timestamp = int((utc + timedelta(seconds=diff_seconds)).timestamp())
    return timestamp, int(diff_hours)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if "mac" not in entry.data:
        # Entry created by v0.4.0 which stored no device data — must be re-added.
        _LOGGER.error(
            "Config entry '%s' has no device config. "
            "Please remove it and add the integration again via the UI.",
            entry.title,
        )
        return False

    hass.data.setdefault(DOMAIN, {})[entry.data["mac"]] = entry

    if not hass.services.has_service(DOMAIN, "set_time"):

        async def set_time(call: ServiceCall) -> None:
            mac = call.data["mac"].upper()

            # Look up stored config for this device (options override data)
            stored_entry = hass.data.get(DOMAIN, {}).get(mac)
            cfg: dict = {}
            if stored_entry is not None:
                cfg = {**stored_entry.data, **stored_entry.options}

            raw_tz_offset = call.data.get("tz_offset")
            tz_offset = int(raw_tz_offset) if raw_tz_offset is not None else None

            raw_timestamp = call.data.get("timestamp")
            timestamp = int(raw_timestamp) if raw_timestamp is not None else None

            ble_device = bluetooth.async_ble_device_from_address(
                hass, mac, connectable=True
            )
            if not ble_device:
                _LOGGER.error("Could not find BLE device '%s'.", mac)
                return

            _LOGGER.info("Found '%s' - attempting to update time.", ble_device)

            # Per-call temp_mode overrides stored config
            raw_temo = call.data.get("temp_mode")
            temo = (
                raw_temo if raw_temo is not None else cfg.get("temp_mode", "")
            ).upper()
            temo_set = False
            if temo in ("C", "F"):
                data_temp_mode = struct.pack("B", 0x01 if temo == "F" else 0xFF)
                temo_set = True

            # Per-call timeout overrides stored config
            raw_timeout = call.data.get("timeout")
            tout = int(
                raw_timeout if raw_timeout is not None else cfg.get("timeout", 60)
            )

            try:
                client = await establish_connection(
                    BleakClient,
                    ble_device,
                    name=mac,
                    max_attempts=3,
                    timeout=tout,
                )
                async with client:
                    if timestamp is None:
                        if tz_offset is not None:
                            # User supplied offset — use raw UTC so offset isn't applied twice.
                            timestamp = int(time.time())
                        else:
                            timestamp, tz_offset = get_localized_timestamp()
                    elif tz_offset is None:
                        _, tz_offset = get_localized_timestamp()

                    data = struct.pack("Ib", timestamp, tz_offset)
                    await client.write_gatt_char(_UUID_TIME, data)
                    if temo_set:
                        await client.write_gatt_char(_UUID_TEMO, data_temp_mode)

                _LOGGER.info(
                    "Done - refreshed time on '%s' to '%s' with offset '%s' hours.",
                    mac,
                    timestamp,
                    tz_offset,
                )
            except Exception:
                _LOGGER.exception("Error updating time on '%s'.", mac)

        hass.services.async_register(DOMAIN, "set_time", set_time)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.data["mac"], None)
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, "set_time")
    return True
