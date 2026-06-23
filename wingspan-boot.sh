#!/usr/bin/env bash
# Pre-start power killswitches for the wingSpan service.
# Runs as root via ExecStartPre=+... in wingspan.service.

set -u

# Stop the ACT LED from blinking on disk activity, then force it off.
if [ -e /sys/class/leds/ACT/trigger ]; then
    echo none > /sys/class/leds/ACT/trigger 2>/dev/null || true
    echo 0    > /sys/class/leds/ACT/brightness 2>/dev/null || true
fi

# Trixie Lite ships with Bluetooth rfkill-soft-blocked. Unblock so the BLE
# peripheral can power on its adapter.
if command -v rfkill >/dev/null 2>&1; then
    rfkill unblock bluetooth 2>/dev/null || true
fi

# BlueZ on Trixie no longer sets the controller discoverable when an LE
# advertisement registers, so Chrome's BLE picker won't see us by default.
# Force discoverable on. (DiscoverableTimeout=0 in /etc/bluetooth/main.conf
# keeps it sticky.)
if command -v bluetoothctl >/dev/null 2>&1; then
    bluetoothctl power on >/dev/null 2>&1 || true
    bluetoothctl discoverable on >/dev/null 2>&1 || true
fi

exit 0
