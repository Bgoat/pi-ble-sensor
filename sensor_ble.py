#!/usr/bin/env python3
"""wingSpan: BLE peripheral exposing SHT40 temp/humidity, USB-mic bee
acoustic analysis, and aggregated hive weight from four BEE-HAUS load
cells (BLE central, see loadcell_central.py).

Run on a Raspberry Pi with:
    sudo apt install python3-dbus python3-gi python3-numpy \
                     python3-sounddevice libportaudio2
    pip install bluezero bleak adafruit-circuitpython-sht4x adafruit-blinka \
                --break-system-packages

Confirm the USB mic shows up with `arecord -l` and adjust AUDIO_DEVICE
below if needed (substring match against the device name).
"""

import json
import os
import threading
import time
import wave
from datetime import datetime, timezone

import adafruit_sht4x
import board
import busio
import numpy as np
import sounddevice as sd
from bluezero import adapter, async_tools, peripheral

import csv_writer
import loadcell_central

SERVICE_UUID = "e80b5ce0-1111-4000-8000-000000000001"
DATA_UUID    = "e80b5ce0-1111-4000-8000-000000000002"
CMD_UUID     = "e80b5ce0-1111-4000-8000-000000000003"

CMD_ZERO_WEIGHT = 0x01

MIC = "i2s"   # "usb" (LavMicro etc.) or "i2s" (SPH0645 via googlevoicehat overlay)

if MIC == "usb":
    AUDIO_DEVICE   = "USB"
    AUDIO_CHANNELS = 1
    AUDIO_DTYPE    = "int16"
elif MIC == "i2s":
    AUDIO_DEVICE   = "voicehat"  # matches "Google voiceHAT SoundCard HiFi voicehat-hifi-0"
    AUDIO_CHANNELS = 2           # I2S hat exposes stereo; only left has real data with SEL→GND
    AUDIO_DTYPE    = "int32"     # SPH0645 outputs 24-bit data left-justified in 32-bit slots
else:
    raise ValueError(f"unknown MIC: {MIC!r}")

SAMPLE_RATE = 48000
BLOCK_SIZE  = 5 * SAMPLE_RATE  # 5s analysis windows

# Raw audio recording for offline frequency analysis. One 5s WAV every
# 2 min is ~469 KB; ~330 MB/day. 3 GB cap → ~9 days rolling window.
SAVE_WAV       = True
AUDIO_DIR      = "/var/lib/wingspan/audio"
WAV_INTERVAL_S = 120
WAV_RETAIN_MB  = 3000

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

i2c = busio.I2C(board.SCL, board.SDA)
sht = adafruit_sht4x.SHT4x(i2c)

audio_state = {
    "db":     -120.0,
    "bands":  {k: -120.0 for k in BANDS},
    "events": [],
}
audio_lock = threading.Lock()


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


_last_wav_save = 0.0


def save_wav(samples_int16: np.ndarray) -> None:
    global _last_wav_save
    now = time.time()
    if now - _last_wav_save < WAV_INTERVAL_S:
        return
    _last_wav_save = now

    dt      = datetime.now(timezone.utc)
    day_dir = os.path.join(AUDIO_DIR, dt.strftime("%Y-%m-%d"))
    path    = os.path.join(day_dir, dt.strftime("%H-%M-%SZ.wav"))
    try:
        os.makedirs(day_dir, exist_ok=True)
        with wave.open(path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(SAMPLE_RATE)
            f.writeframes(samples_int16.tobytes())
    except OSError as e:
        print(f"[wav] write failed: {e}")
        return
    enforce_wav_cap()


def enforce_wav_cap() -> None:
    cap_bytes = WAV_RETAIN_MB * 1024 * 1024
    files = []
    for root, _, names in os.walk(AUDIO_DIR):
        for n in names:
            if not n.endswith(".wav"):
                continue
            p = os.path.join(root, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, p))
    total = sum(s for _, s, _ in files)
    if total <= cap_bytes:
        return
    files.sort()
    for _, size, p in files:
        if total <= cap_bytes:
            break
        try:
            os.remove(p)
            total -= size
        except OSError:
            continue


def audio_worker():
    stream = sd.InputStream(
        device=AUDIO_DEVICE,
        channels=AUDIO_CHANNELS,
        samplerate=SAMPLE_RATE,
        dtype=AUDIO_DTYPE,
        blocksize=BLOCK_SIZE,
    )
    stream.start()
    while True:
        data, _ = stream.read(BLOCK_SIZE)
        if AUDIO_DTYPE == "int32":
            # SPH0645 has a large DC offset; strip it before the int16 cast
            # so saved WAVs don't have a giant 0 Hz spike.
            raw = data[:, 0].astype(np.int64)
            raw -= int(raw.mean())
            mono = (raw >> 16).astype(np.int16)
        else:
            mono = data[:, 0]
        db, bands, events = analyze(mono)
        with audio_lock:
            audio_state["db"]     = db
            audio_state["bands"]  = bands
            audio_state["events"] = events
        if SAVE_WAV:
            save_wav(mono)


def start_audio():
    t = threading.Thread(target=audio_worker, daemon=True)
    t.start()
    return t


def csv_logger_worker():
    while True:
        time.sleep(60)
        try:
            temp_c, rh = sht.measurements
            with audio_lock:
                db     = audio_state["db"]
                bands  = dict(audio_state["bands"])
                events = list(audio_state["events"])
            weight = loadcell_central.get_state()
            row = [
                int(time.time()),
                round(temp_c, 2),
                round(rh, 2),
                weight["total_kg"],
                db,
                "", "", "",   # bv, bp, chg — pending MAX17048 wire-up
                bands["hum"],
                bands["workers"],
                bands["queen"],
                bands["swarm"],
                ",".join(events),
            ]
            csv_writer.append(row)
        except Exception as e:
            print(f"[csv] logger error: {e}")


def start_csv_logger():
    t = threading.Thread(target=csv_logger_worker, daemon=True)
    t.start()
    return t


def read_payload():
    temp_c, rh = sht.measurements
    with audio_lock:
        db     = audio_state["db"]
        bands  = dict(audio_state["bands"])
        events = list(audio_state["events"])
    weight = loadcell_central.get_state()
    payload = {
        "t":      round(temp_c, 2),
        "h":      round(rh, 2),
        "db":     db,
        "bands":  bands,
        "events": events,
        "w":      weight["total_kg"],
        "w_legs": {leg: v["kg"]       for leg, v in weight["legs"].items()},
        "bat":    {leg: v["batt_pct"] for leg, v in weight["legs"].items()},
        "conn":   {leg: v["connected"] for leg, v in weight["legs"].items()},
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
    if value and value[0] == CMD_ZERO_WEIGHT:
        loadcell_central.send_tare_all()
        print("[cmd] tare load cells")


def main():
    start_audio()
    start_csv_logger()
    loadcell_central.start()

    adapter_addr = list(adapter.Adapter.available())[0].address
    dev = peripheral.Peripheral(adapter_addr, local_name="wingSpan-1")
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
