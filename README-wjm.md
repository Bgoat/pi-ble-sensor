# wingSpan unit for wjm — hardware addendum

Read this first to know what's in the package and how everything physically connects. For software setup (Tailscale, SSH/SCP, the BLE web app) see [README.md](README.md).

---

## What's in the package

### Compute & sensors (assembled inside the enclosure)

- **Raspberry Pi Zero 2 W** — the brain. Runs the sensor service that records audio and logs CSV data.
- **SHT40 temperature & humidity sensor** — Adafruit #4885 on the STEMMA QT I²C chain. Reads ambient temp/humidity once per minute.
- **SPH0645 I²S MEMS microphone** — Adafruit #3421. Captures 5 seconds of audio every 2 minutes for offline frequency analysis.

### Power & battery

- **Adafruit BQ24074 LiPo charger w/ load-sharing PCB** — Adafruit #4755. Charges the LiPo from the solar panel and switches between solar and battery automatically. Includes a USB-C input for bench-charging if you ever need it.
- **Pololu 0J12777 step-up regulator (5 V output)** — boosts the LiPo's 3.0–4.2 V up to a clean 5 V for the Pi.
- **3.7 V 10,050 mAh LiPo battery** — main energy storage. JST-PH 2.0 connector.

### Solar kit (Voltaic Systems)

- **P120** — 20 W 6 V ETFE solar panel. ETFE coating is UV- and weather-resistant.
- **BK103** — large mounting bracket for the panel.
- **K-MT-BK-ETFE** — screws + washers for fastening the panel to the bracket.
- **W036** — 3.5×1.1 mm extension cable, 4 ft. Connects the panel to the BQ24074's DC input.

---

## How it all connects

```
Solar panel (P120, 6 V)
        │
        │  W036 extension cable (3.5×1.1 mm barrel)
        ▼
  BQ24074  ──BAT──►  LiPo battery (10050 mAh)
  charger
        │
        │  SYS output (auto-selects solar or battery)
        ▼
  Pololu 0J12777 step-up  ──5 V──►  Raspberry Pi Zero 2 W
                                          │
                                          ├── I²C ──► SHT40 (STEMMA QT)
                                          └── I²S ──► SPH0645 microphone
```

Everything except the solar panel itself lives inside the enclosure. The W036 cable is the only thing you need to route between them.

---

## Installation

1. **Mount the solar panel.**
   - Bolt the P120 panel onto the BK103 bracket using the K-MT-BK-ETFE screws and washers.
   - Position the bracket so the panel faces south (northern hemisphere) and isn't shaded by the hive lid, tree branches, or anything else during the productive part of the day.
   - Tilt angle isn't critical — anywhere from horizontal to ~30° works.

2. **Connect the panel to the unit.**
   - Plug one end of the W036 cable into the panel's output.
   - Route the cable to the enclosure and plug the other end into the BQ24074's barrel-jack input. **Polarity is fixed by the barrel jack, so you can't get it wrong.**

3. **Place the unit near or on the hive.**
   - The mic and SHT40 sensor are inside the enclosure but exposed to ambient air through a vent. Place the unit close enough to the hive that internal bee sounds are audible (within a few feet, or directly on the lid).
   - Keep the unit upright so the vent isn't pointed straight at the ground.

4. **First boot.**
   - As long as the battery has charge OR the solar panel is plugged in and getting sun, the Pi will boot automatically (~30 seconds).
   - It will join your `wjm` WiFi and bring up Tailscale on its own.
   - Verify by `ssh beehaus@raspberrypi` from your laptop per the main README.

---

## Battery & solar safety

- **Don't puncture, crush, drop, or expose the LiPo battery to high heat.** Damaged LiPo cells can vent flammable gas or catch fire. If the enclosure ever feels unusually hot or smells acrid, **unplug the solar panel and contact William immediately**.
- The BQ24074 has built-in overcharge / overdischarge protection. Don't bypass it or attempt to charge the battery directly.
- The panel is rated to **20 W at 6 V (open-circuit ~7.5 V)** — within the BQ24074's safe input range. Don't substitute a higher-voltage panel without checking with William.
- If you need to disconnect the panel temporarily (e.g. relocating the unit), unplug at the barrel jack — never yank by the cable.

---

## What to expect day-to-day

- **In sun:** the BQ24074's charge LED will be on. The battery will top up; the Pi runs from solar with battery as ballast.
- **At night / cloudy:** the unit runs from battery alone. A fully charged 10,050 mAh battery should easily power the Pi for multiple days without sun.
- **Sustained no sun for >5 days:** the battery may eventually drop low enough that the BQ24074 cuts power to protect the cells. The Pi will reboot once solar power returns. Any data already on disk (audio, CSV) is preserved.

You don't need to do anything to maintain the system. Just pull data over Tailscale per the main README.

---

## What's already configured on the Pi

- `wjm` WiFi credentials pre-loaded — joins automatically on boot.
- Tailscale installed and authorized. William will share the device with your Tailscale account.
- `wingspan.service` (systemd) auto-starts the sensor on boot and restarts it if it crashes.
- Data lives in `/var/lib/wingspan/`:
  - `audio/YYYY-MM-DD/HH-MM-SSZ.wav` — 5-second clips every 2 minutes
  - `log.csv` — one row per minute

---

## If something looks wrong

- **No green/yellow LED on the BQ24074 in sun** → check the W036 cable seating at both ends.
- **Pi never comes online over Tailscale** → bring the unit indoors, plug the BQ24074's USB-C into a wall charger to confirm it boots without solar. If it still doesn't show up, contact William.
- **Pi reboots constantly** → battery may be exhausted and solar isn't keeping up. Bench-charge via the BQ24074 USB-C for a few hours.

For anything else, text William.
