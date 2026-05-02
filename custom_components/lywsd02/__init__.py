from __future__ import annotations

import time
import struct
import logging

from datetime import datetime, timezone, timedelta

from bleak import BleakClient
from bleak_retry_connector import establish_connection

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
    async def set_time(call: ServiceCall) -> None:
        mac = call.data["mac"].upper()
        if not mac:
            _LOGGER.error(
                "The 'mac' parameter is missing from service call: %s", call.data
            )
            return

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

        temo_set = False
        temo = (call.data.get("temp_mode") or "").upper()

        if temo in ("C", "F"):
            data_temp_mode = struct.pack("B", 0x01 if temo == "F" else 0xFF)
            temo_set = True

        tout = int(call.data.get("timeout", 60))

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
