#!/usr/bin/env python3
"""One-time per-leg load cell calibration.

Each BEE-HAUS cell ships uncalibrated. Calibration is two steps and
lives on the device (persists across power cycles per nRF52 firmware):

    1. tare      — put nothing on the cell, send zero-offset command
    2. scale     — put a known mass on the cell, send scale = mass / reading

Stop wingspan.service first so its central isn't competing for the cell:

    sudo systemctl stop wingspan
    python3 calibrate_loadcell.py --tare      AA:BB:CC:DD:EE:FF
    python3 calibrate_loadcell.py --scale 500 AA:BB:CC:DD:EE:FF
    sudo systemctl start wingspan

The --scale argument is the known mass in grams.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys

from bleak import BleakClient

NUS_TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

PACKET_DATA_NOTIFY     = 1
PACKET_ZERO_OFFSET_SET = 2
PACKET_SCALE_SET       = 3


def _build(ptype: int, payload: bytes = b"") -> bytes:
    return struct.pack("<BBH", ptype, len(payload), 0) + payload


async def _read_weight_g(client: BleakClient, samples: int = 8) -> float:
    """Average the next N weight notifications."""
    readings: list[float] = []
    done = asyncio.Event()

    def handler(_char, data: bytearray) -> None:
        if len(data) >= 13 and data[0] == PACKET_DATA_NOTIFY and data[1] == 9:
            w, _v, _p = struct.unpack_from("<2fB", data, 4)
            readings.append(w)
            if len(readings) >= samples:
                done.set()

    await client.start_notify(NUS_RX_UUID, handler)
    try:
        await asyncio.wait_for(done.wait(), timeout=15.0)
    finally:
        await client.stop_notify(NUS_RX_UUID)
    return sum(readings) / len(readings)


async def tare(mac: str) -> None:
    async with BleakClient(mac) as client:
        print(f"connected to {mac}")
        await client.write_gatt_char(NUS_TX_UUID, _build(PACKET_ZERO_OFFSET_SET),
                                     response=False)
        print("sent tare. allow ~2s, then verify by reading the cell.")
        await asyncio.sleep(2.0)
        live = await _read_weight_g(client, samples=4)
        print(f"post-tare reading: {live:+.2f} g (expect ~0)")


async def scale(mac: str, known_g: float) -> None:
    async with BleakClient(mac) as client:
        print(f"connected to {mac}, sampling current reading...")
        current = await _read_weight_g(client)
        print(f"current reading: {current:.2f} g")
        if abs(current) < 1e-3:
            print("reading is ~0; tare first, or apply mass.", file=sys.stderr)
            sys.exit(1)
        factor = known_g / current
        print(f"sending scale = known/current = {known_g}/{current:.2f} = {factor:.6f}")
        await client.write_gatt_char(NUS_TX_UUID,
                                     _build(PACKET_SCALE_SET,
                                            struct.pack("<f", factor)),
                                     response=False)
        await asyncio.sleep(2.0)
        live = await _read_weight_g(client, samples=4)
        print(f"post-scale reading: {live:.2f} g (expect ~{known_g})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--tare", action="store_true", help="zero-offset the cell")
    g.add_argument("--scale", type=float, metavar="GRAMS",
                   help="set scale using a known mass on the cell (grams)")
    p.add_argument("mac", help="cell MAC address, e.g. AA:BB:CC:DD:EE:FF")
    args = p.parse_args()

    if args.tare:
        asyncio.run(tare(args.mac.upper()))
    else:
        asyncio.run(scale(args.mac.upper(), args.scale))


if __name__ == "__main__":
    main()
