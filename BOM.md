# wingSpan — Bill of Materials

Per-unit hardware for one solar-powered hive sensor. Scale: 1 unit now, 5 eventually.

## Core compute & power

| # | Item | Part / Source | Qty | Unit cost | Notes |
|---|---|---|---|---|---|
| 1 | Raspberry Pi Zero 2 W | rpilocator.com / Adafruit / Pimoroni | 1 | ~$15 | Often supply-constrained; watch for marked-up resellers. |
| 2 | microSD card, 32 GB | Samsung EVO Plus A1 / SanDisk Ultra | 1 | ~$8 | Class 10 / A1 minimum. |
| 3 | LiPo battery, 10050 mAh, 3.7 V | (already owned) | 1 | $0 / ~$25 new | JST-PH 2.0 connector. |
| 4 | BQ24074 USB/DC/Solar charger | Adafruit #4755 | 1 | $17.50 | Load-sharing power path. Already owned for unit 1. |
| 5 | Buck-boost 5 V regulator | Pololu S13V30F5 (#4082) | 1 | $14.95 | 2.8–22 V → 5 V @ 3 A. Already owned for unit 1. |
| 6 | Solar panel, 5–6 V / 1–2 W | (already owned) | 1 | $0 / ~$10 | Voc must stay ≤ 10 V for BQ24074 input. |

## Sensors

| # | Item | Part / Source | Qty | Unit cost | Notes |
|---|---|---|---|---|---|
| 7 | SHT40 temp/humidity | Adafruit #4885 (STEMMA QT) | 1 | $4.95 | I²C, address 0x44. |
| 8 | **MAX17048 LiPo fuel gauge** | Adafruit #5580 (STEMMA QT) | 1 | $4.95 | **New addition** — battery %, voltage, charge rate. I²C, address 0x36. |
| 9a | USB mini microphone | generic | 1 | ~$8 | Default mic for airborne hum / flight (200–270 Hz). |
| 9b | SPH0645 I²S microphone | Adafruit #3421 | 0–1 | $6.95 | Optional — for units placed against comb (catches piping, stop signals, waggle). 5-wire solder, ~20 min install. |

## Wiring & connectors

| # | Item | Part / Source | Qty | Unit cost | Notes |
|---|---|---|---|---|---|
| 10 | STEMMA QT / Qwiic cable, 50 mm | Adafruit #4399 | 2–3 | $0.95 | Chains SHT40 + MAX17048 (+ optional accessory). |
| 11 | JST-PH 2.0 cable pigtails | Adafruit #261 / generic 10-pack | 2 | $0.50 | Battery + solar inputs. |
| 12 | Pi GPIO header (if not pre-soldered) | Adafruit #3413 | 1 | $0.95 | Pi Zero 2 W often ships headerless. |
| 13 | Silicone hookup wire, 26 AWG | Adafruit #1444 pack | shared | $16 | Charger ↔ regulator ↔ Pi 5 V. |
| 14 | Heat-shrink assortment | generic | shared | $5 | |
| 15 | Solder, flux | already owned | — | — | |

## Enclosure (parallel track — not in initial plan)

| # | Item | Notes |
|---|---|---|
| 16 | 3D-printed weather-resistant box | Ventilation slot facing SHT40 + mic; UV-stable PETG or ASA. Spec later. |
| 17 | Mounting hardware | Velcro / screws / strap depending on hive style. |

## Shared tools (one-time, not per-unit)

| # | Item | Source | Cost | Notes |
|---|---|---|---|---|
| T1 | Inline USB power meter | "RD UM25C" or similar | $10–15 | Verifies Session 1 power target. |
| T2 | Soldering iron + multimeter | already owned | — | |
| T3 | SD card flasher | Raspberry Pi Imager (free) | — | |

---

## Per-unit cost summary

| Scenario | Subtotal |
|---|---|
| Unit 1, using already-owned battery / charger / regulator / mic / panel | **~$33** (sensors + microSD + Pi + cables) |
| Units 2–5, fully new (no I²S mic) | **~$72 each** |
| Units 2–5, fully new with SPH0645 instead of USB | **~$71 each** |

**5-unit project total (assuming unit 1 reuses owned parts):** ~$33 + 4 × $72 ≈ **$320** in parts + ~$15 for the USB power meter.

## Ordering notes

- **Adafruit STEMMA QT chain** keeps the I²C wiring solder-free: Pi → SHT40 → MAX17048. Add a Pi STEMMA QT adapter (#5985, $2.50) if you'd rather not solder I²C to the GPIO header at all.
- Order **+1 spare** of MAX17048, SHT40, microSD, and Pi Zero 2 W. Each is a single-point-of-failure during build.
- BQ24074 solar input wants a panel with Voc ≤ 10 V. Confirm your panels' open-circuit voltage in full sun before connecting — cells in series can exceed this.
- Don't ship past Session 3 without an enclosure plan; bees will propolize anything reachable.
