"""BLE central that reads four BEE-HAUS load cells and aggregates weight.

Each load cell is an nRF52 peripheral advertising local name "BEE-HAUS..."
and exposing the Nordic UART service. On notify, it streams a 13-byte
frame every ~tick:

    offset  size  field
    0       1     packet_type      (uint8, expect 1 = DEVICE_DATA_NOTIFY)
    1       1     payload_length   (uint8, expect 9)
    2       2     msg_index        (uint16 LE)
    4       4     weight           (float32 LE, grams — see notes)
    8       4     battery_voltage  (float32 LE, volts)
    12      1     battery_capacity (uint8, percent)

Calibration (zero offset + scale) lives on the device. The Pi sends:

    type=2 (PACKET_CMD_LOADCELL_ZERO_OFFSET_SET)  — header only, no payload
    type=3 (PACKET_CMD_SET_CALIBRATION_DATA)      — payload: float32 LE scale,
            where scale = known_mass_g / current_reading_g

Outbound frames use the same header; the length byte counts payload only.

Protocol is reverse-engineered from hydratech-iot/bee-haus-pc-app
(ble_streaming_tool.py + ble_thread.py). The "grams" interpretation of
the weight float is inferred from the |w|<1 deadband in that app and
needs firmware-side confirmation — the conversion divisor below is the
single knob to change if it turns out to be something else.
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import threading
import time
from typing import Optional

from bleak import BleakClient, BleakScanner

NAME_PREFIX = "BEE-HAUS"

NUS_TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # central -> device (write)
NUS_RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # device -> central (notify)

PACKET_DATA_NOTIFY     = 1
PACKET_ZERO_OFFSET_SET = 2
PACKET_SCALE_SET       = 3

GRAMS_PER_KG = 1000.0

LEGS = ("FL", "FR", "BL", "BR")

# Fill in once the four cells are paired with known leg positions. Keys
# are leg labels, values are uppercase MACs (Linux format "AA:BB:..").
# Any leg left as None falls through to discovery-by-order on first run.
LEG_MAP: dict[str, Optional[str]] = {
    "FL": None,
    "FR": None,
    "BL": None,
    "BR": None,
}

LEG_MAP_PATH = "/var/lib/wingspan/legs.json"

SCAN_INTERVAL_S    = 5.0
RECONNECT_BACKOFF_S = (1, 2, 5, 10, 30)  # capped at the last entry

_state_lock = threading.Lock()
_state: dict = {
    "total_kg": 0.0,
    "legs":     {leg: {"kg": None, "batt_v": None, "batt_pct": None,
                       "mac": None, "connected": False, "last_seen": 0.0}
                 for leg in LEGS},
}

_clients: dict[str, BleakClient] = {}
_loop: Optional[asyncio.AbstractEventLoop] = None


def get_state() -> dict:
    """Snapshot of current weight + per-leg detail for the BLE payload."""
    with _state_lock:
        return {
            "total_kg": _state["total_kg"],
            "legs": {leg: dict(v) for leg, v in _state["legs"].items()},
        }


def _load_persisted_map() -> None:
    try:
        with open(LEG_MAP_PATH) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return
    for leg in LEGS:
        mac = saved.get(leg)
        if mac and LEG_MAP[leg] is None:
            LEG_MAP[leg] = mac.upper()


def _persist_map() -> None:
    try:
        os.makedirs(os.path.dirname(LEG_MAP_PATH), exist_ok=True)
        with open(LEG_MAP_PATH, "w") as f:
            json.dump({leg: LEG_MAP[leg] for leg in LEGS}, f)
    except OSError as e:
        print(f"[loadcell] persist failed: {e}")


def _recompute_total() -> None:
    total = 0.0
    for leg, v in _state["legs"].items():
        if v["connected"] and v["kg"] is not None:
            total += v["kg"]
    _state["total_kg"] = round(total, 3)


def _make_notify_handler(leg: str):
    def handler(_char, data: bytearray) -> None:
        if len(data) < 4:
            return
        ptype, plen = data[0], data[1]
        if ptype != PACKET_DATA_NOTIFY or plen != 9 or len(data) < 13:
            return
        weight_g, batt_v, batt_pct = struct.unpack_from("<2fB", data, 4)
        kg = weight_g / GRAMS_PER_KG
        with _state_lock:
            slot = _state["legs"][leg]
            slot["kg"]        = round(kg, 3)
            slot["batt_v"]    = round(float(batt_v), 2)
            slot["batt_pct"]  = int(batt_pct)
            slot["last_seen"] = time.time()
            _recompute_total()
    return handler


def _build_packet(ptype: int, payload: bytes = b"") -> bytes:
    # Outbound length byte counts payload only, not the header.
    return struct.pack("<BBH", ptype, len(payload), 0) + payload


async def _maintain_leg(leg: str) -> None:
    """Per-leg connect / notify / reconnect loop."""
    attempt = 0
    while True:
        mac = LEG_MAP[leg]
        if mac is None:
            await asyncio.sleep(SCAN_INTERVAL_S)
            continue

        try:
            async with BleakClient(mac) as client:
                _clients[leg] = client
                with _state_lock:
                    _state["legs"][leg]["mac"]       = mac
                    _state["legs"][leg]["connected"] = True
                await client.start_notify(NUS_RX_UUID, _make_notify_handler(leg))
                print(f"[loadcell] {leg} connected ({mac})")
                attempt = 0
                while client.is_connected:
                    await asyncio.sleep(1.0)
        except Exception as e:
            print(f"[loadcell] {leg} ({mac}) error: {e}")
        finally:
            _clients.pop(leg, None)
            with _state_lock:
                _state["legs"][leg]["connected"] = False
                _state["legs"][leg]["kg"]        = None
                _recompute_total()

        delay = RECONNECT_BACKOFF_S[min(attempt, len(RECONNECT_BACKOFF_S) - 1)]
        attempt += 1
        await asyncio.sleep(delay)


async def _discover_and_assign() -> None:
    """Populate any unmapped leg with the first unseen BEE-HAUS* MAC."""
    while any(LEG_MAP[leg] is None for leg in LEGS):
        unassigned = [leg for leg in LEGS if LEG_MAP[leg] is None]
        known = {LEG_MAP[leg] for leg in LEGS if LEG_MAP[leg]}
        try:
            devices = await BleakScanner.discover(timeout=SCAN_INTERVAL_S,
                                                  return_adv=True)
        except Exception as e:
            print(f"[loadcell] scan error: {e}")
            await asyncio.sleep(SCAN_INTERVAL_S)
            continue

        for dev, adv in devices.values():
            name = (adv.local_name or dev.name or "")
            mac  = dev.address.upper()
            if not name.startswith(NAME_PREFIX) or mac in known:
                continue
            if not unassigned:
                break
            leg = unassigned.pop(0)
            LEG_MAP[leg] = mac
            known.add(mac)
            print(f"[loadcell] discovered {name} @ {mac} -> {leg}")
            _persist_map()
        await asyncio.sleep(SCAN_INTERVAL_S)


async def _run() -> None:
    _load_persisted_map()
    asyncio.create_task(_discover_and_assign())
    await asyncio.gather(*(_maintain_leg(leg) for leg in LEGS))


def _thread_target() -> None:
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_run())
    except Exception as e:
        print(f"[loadcell] worker crashed: {e}")


def start() -> threading.Thread:
    t = threading.Thread(target=_thread_target, name="loadcell", daemon=True)
    t.start()
    return t


async def _broadcast(packet: bytes) -> None:
    for leg, client in list(_clients.items()):
        if not client.is_connected:
            continue
        try:
            await client.write_gatt_char(NUS_TX_UUID, packet, response=False)
        except Exception as e:
            print(f"[loadcell] {leg} write failed: {e}")


def send_tare_all() -> None:
    """Zero every connected leg. Safe to call from another thread."""
    if _loop is None:
        print("[loadcell] tare ignored: worker not started")
        return
    pkt = _build_packet(PACKET_ZERO_OFFSET_SET)
    asyncio.run_coroutine_threadsafe(_broadcast(pkt), _loop)


def send_scale(leg: str, scale: float) -> None:
    """Set the per-leg scale factor (known_mass_g / current_reading_g)."""
    if _loop is None:
        print("[loadcell] scale ignored: worker not started")
        return
    client = _clients.get(leg)
    if client is None or not client.is_connected:
        print(f"[loadcell] scale ignored: {leg} not connected")
        return
    pkt = _build_packet(PACKET_SCALE_SET, struct.pack("<f", float(scale)))

    async def _send():
        try:
            await client.write_gatt_char(NUS_TX_UUID, pkt, response=False)
        except Exception as e:
            print(f"[loadcell] {leg} scale write failed: {e}")

    asyncio.run_coroutine_threadsafe(_send(), _loop)
