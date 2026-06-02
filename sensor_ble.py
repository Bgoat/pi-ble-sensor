#!/usr/bin/env python3
"""BLE peripheral exposing SHT40 temp/humidity and SPH0645 sound metrics.

Run on a Raspberry Pi with:
    sudo apt install python3-dbus python3-gi libportaudio2
    pip install bluezero adafruit-circuitpython-sht4x adafruit-blinka \
                sounddevice numpy

For the SPH0645 you need an I2S overlay enabled, e.g. in
/boot/firmware/config.txt:
    dtparam=i2s=on
    dtoverlay=googlevoicehat-soundcard
then reboot. Confirm with `arecord -l` that the mic shows up as a card.
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

SAMPLE_RATE = 16000
BLOCK_SIZE  = SAMPLE_RATE  # 1s analysis windows

i2c = busio.I2C(board.SCL, board.SDA)
sht = adafruit_sht4x.SHT4x(i2c)

sound_state = {"db": -120.0, "label": "silent"}
sound_lock  = threading.Lock()


def classify(db: float) -> str:
    if db < -55: return "silent"
    if db < -40: return "quiet"
    if db < -25: return "speech"
    if db < -10: return "loud"
    return "very_loud"


def audio_callback(indata, frames, t, status):
    # SPH0645 ships 24-bit samples in 32-bit I2S frames; treat as int32
    # and normalise. Subtract mean to drop the mic's DC offset.
    samples = indata[:, 0].astype(np.float32) / (2 ** 31)
    samples -= samples.mean()
    rms = float(np.sqrt(np.mean(samples ** 2)) + 1e-12)
    db  = 20.0 * np.log10(rms)  # dBFS
    with sound_lock:
        sound_state["db"]    = round(db, 1)
        sound_state["label"] = classify(db)


def start_audio():
    stream = sd.InputStream(
        channels=1,
        samplerate=SAMPLE_RATE,
        dtype="int32",
        blocksize=BLOCK_SIZE,
        callback=audio_callback,
    )
    stream.start()
    return stream


def read_payload():
    temp_c, rh = sht.measurements
    with sound_lock:
        db    = sound_state["db"]
        label = sound_state["label"]
    payload = {
        "t":     round(temp_c, 2),
        "h":     round(rh, 2),
        "db":    db,
        "label": label,
        "ts":    int(time.time()),
    }
    return list(json.dumps(payload).encode("utf-8"))


def on_read(options):
    return read_payload()


def push_update(characteristic):
    characteristic.set_value(read_payload())
    return characteristic.is_notifying  # keep timer alive while subscribed


def on_notify(notifying, characteristic):
    if notifying:
        async_tools.add_timer_seconds(1, push_update, characteristic)


def main():
    start_audio()

    adapter_addr = list(adapter.Adapter.available())[0].address
    pi_sensor = peripheral.Peripheral(adapter_addr, local_name="PiSensor")
    pi_sensor.add_service(srv_id=1, uuid=SERVICE_UUID, primary=True)
    pi_sensor.add_characteristic(
        srv_id=1,
        chr_id=1,
        uuid=DATA_UUID,
        value=[],
        notifying=False,
        flags=["read", "notify"],
        read_callback=on_read,
        notify_callback=on_notify,
    )
    pi_sensor.publish()


if __name__ == "__main__":
    main()
