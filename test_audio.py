#!/usr/bin/env python3
"""Isolated audio capture test — runs the same numpy math as the main
script but with no BLE involved. Use this to confirm whether the SIGILL
is coming from the audio path."""

import numpy as np
import sounddevice as sd

AUDIO_DEVICE = "USB"
SAMPLE_RATE  = 48000
BLOCK_SIZE   = SAMPLE_RATE  # 1s windows


def cb(indata, frames, time_info, status):
    if status:
        print("status:", status)
    samples = indata[:, 0].astype(np.float32) / (2 ** 15)
    samples -= samples.mean()
    rms = float(np.sqrt(np.mean(samples ** 2)) + 1e-12)
    db  = 20.0 * np.log10(rms)
    print(f"dBFS: {db:6.1f}   peak: {float(np.max(np.abs(samples))):.4f}")


def main():
    print("Devices:")
    print(sd.query_devices())
    print()
    print(f"Opening device '{AUDIO_DEVICE}' @ {SAMPLE_RATE} Hz...")
    with sd.InputStream(
        device=AUDIO_DEVICE,
        channels=1,
        samplerate=SAMPLE_RATE,
        dtype="int16",
        blocksize=BLOCK_SIZE,
        callback=cb,
    ):
        sd.sleep(5000)
    print("Done.")


if __name__ == "__main__":
    main()
