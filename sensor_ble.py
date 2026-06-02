#!/usr/bin/env python3
"""wingSpan: BLE peripheral exposing SHT40 temp/humidity, USB-mic bee
acoustic analysis, and a placeholder hive weight.

Run on a Raspberry Pi with:
    sudo apt install python3-dbus python3-gi python3-numpy \
                     python3-sounddevice libportaudio2
    pip install bluezero adafruit-circuitpython-sht4x adafruit-blinka \
                --break-system-packages

Confirm the USB mic shows up with `arecord -l` and adjust AUDIO_DEVICE
below if needed (substring match against the device name).
"""

import json
import threading
import time

import adafruit_sht4x
import board
import busio
import numpy as np
import sounddevice as sd
from bluezero import adapter, async_tools, peripheral

SERVICE_UUID = "e80b5ce0-1111-4000-8000-000000000001"
DATA_UUID    = "e80b5ce0-1111-4000-8000-000000000002"
CMD_UUID     = "e80b5ce0-1111-4000-8000-000000000003"

CMD_ZERO_WEIGHT = 0x01

AUDIO_DEVICE = "USB"
SAMPLE_RATE  = 48000
BLOCK_SIZE   = SAMPLE_RATE  # 1s analysis windows

# Bee acoustic bands (Hz). "hum" is the 125 Hz resting baseline that you
# subtract before judging the others — it otherwise swamps weaker signals.
BANDS = {
    "hum":     (100, 150),   # resting colony hum — baseline
    "workers": (200, 270),   # flight, general activity, warble, waggle
    "queen":   (320, 450),   # queen tooting (~400) and quacking (~350)
    "swarm":   (400, 500),   # elevated energy here is a swarm marker
}

# Each band must be this many dB above the 125 Hz hum to count as active.
EVENT_THRESHOLD_DB = {
    "workers": 8.0,
    "queen":   10.0,
    "swarm":   8.0,
}

# Static placeholder until a real load cell is wired up.
DEFAULT_WEIGHT_KG = 12.345

i2c = busio.I2C(board.SCL, board.SDA)
sht = adafruit_sht4x.SHT4x(i2c)

audio_state = {
    "db":     -120.0,
    "bands":  {k: -120.0 for k in BANDS},
    "events": [],
}
audio_lock = threading.Lock()

weight_kg   = DEFAULT_WEIGHT_KG
weight_lock = threading.Lock()


def analyze(samples_int16: np.ndarray):
    x = samples_int16.astype(np.float32) / 32768.0
    x -= x.mean()

    rms = float(np.sqrt(np.mean(x ** 2)) + 1e-12)
    db_overall = 20.0 * np.log10(rms)

    win   = np.hanning(len(x)).astype(np.float32)
    spec  = np.abs(np.fft.rfft(x * win)) ** 2
    freqs = np.fft.rfftfreq(len(x), 1.0 / SAMPLE_RATE)

    band_db = {}
    for name, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        p = float(spec[mask].mean()) if mask.any() else 1e-20
        band_db[name] = round(10.0 * np.log10(p + 1e-20), 1)

    hum_db = band_db["hum"]
    events = [
        name for name, thresh in EVENT_THRESHOLD_DB.items()
        if band_db[name] - hum_db > thresh
    ]
    return round(db_overall, 1), band_db, events


def audio_worker():
    stream = sd.InputStream(
        device=AUDIO_DEVICE,
        channels=1,
        samplerate=SAMPLE_RATE,
        dtype="int16",
        blocksize=BLOCK_SIZE,
    )
    stream.start()
    while True:
        data, _ = stream.read(BLOCK_SIZE)
        db, bands, events = analyze(data[:, 0])
        with audio_lock:
            audio_state["db"]     = db
            audio_state["bands"]  = bands
            audio_state["events"] = events


def start_audio():
    t = threading.Thread(target=audio_worker, daemon=True)
    t.start()
    return t


def read_payload():
    temp_c, rh = sht.measurements
    with audio_lock:
        db     = audio_state["db"]
        bands  = dict(audio_state["bands"])
        events = list(audio_state["events"])
    with weight_lock:
        w = weight_kg
    payload = {
        "t":      round(temp_c, 2),
        "h":      round(rh, 2),
        "db":     db,
        "bands":  bands,
        "events": events,
        "w":      round(w, 3),
        "ts":     int(time.time()),
    }
    return list(json.dumps(payload).encode("utf-8"))


def on_read(options):
    return read_payload()


def push_update(characteristic):
    characteristic.set_value(read_payload())
    return characteristic.is_notifying


def on_notify(notifying, characteristic):
    if notifying:
        async_tools.add_timer_seconds(1, push_update, characteristic)


def on_cmd_write(value, options):
    global weight_kg
    if value and value[0] == CMD_ZERO_WEIGHT:
        with weight_lock:
            weight_kg = 0.0
        print("[cmd] zero weight")


def main():
    start_audio()

    adapter_addr = list(adapter.Adapter.available())[0].address
    dev = peripheral.Peripheral(adapter_addr, local_name="wingSpan")
    dev.add_service(srv_id=1, uuid=SERVICE_UUID, primary=True)
    dev.add_characteristic(
        srv_id=1, chr_id=1, uuid=DATA_UUID,
        value=[], notifying=False,
        flags=["read", "notify"],
        read_callback=on_read,
        notify_callback=on_notify,
    )
    dev.add_characteristic(
        srv_id=1, chr_id=2, uuid=CMD_UUID,
        value=[], notifying=False,
        flags=["write"],
        write_callback=on_cmd_write,
    )
    dev.publish()


if __name__ == "__main__":
    main()
