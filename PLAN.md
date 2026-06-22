# wingSpan — Build & Deploy Plan

Goal: 5 solar-powered, BLE-connected hive sensors. Each reports temperature, humidity, hive weight, sound level, and bee-acoustic events; logs locally; syncs to phone on demand.

Cadence: a few hours per session, one session per day. Total ~14 h spread over ~5 sessions for the first deployable unit, plus replication time for the remaining four.

---

## Decisions locked in

| Decision | Choice |
|---|---|
| Battery telemetry | MAX17048 fuel gauge on I²C, plus BQ24074 `PG` pin to a GPIO for "input present" |
| RTC | None — phone writes current epoch on connect; pre-sync rows marked with `ts=0` and interpolated by the phone using `(last_sync, monotonic_uptime)` |
| CSV retention | 200 MB cap; rotate oldest 10% when hit (~3.8 years at 1 row/min) |
| Reporting cadence | One CSV row per minute on the Pi; BLE notification once per minute |
| Audio duty cycle | Open mic, capture 1 s, analyze, close mic, sleep ~59 s |
| Mic choice | Per-unit flag (`MIC = "usb"` or `"i2s"`); USB by default, SPH0645 for units placed against comb |
| Unit naming | `wingSpan-1` … `wingSpan-5`, set per-Pi |
| Auto-start | systemd service `wingspan.service`, `Restart=always` |
| Wi-Fi at runtime | Off (`rfkill block wifi`); BLE only |

---

## Session 1 — Power-optimized firmware (~3 h)

**Goal:** one prototype Pi draws < 100 mA average from the 5 V rail.

Tasks:
1. Refactor `audio_worker()` to duty-cycle: open `sd.InputStream`, read 1 s, close, sleep until next minute boundary.
2. Add boot-time killswitches via a small `wingspan-boot.sh` invoked from `wingspan.service` `ExecStartPre=`:
   - `rfkill block wifi`
   - `/usr/bin/tvservice -o`
   - `echo 0 > /sys/class/leds/ACT/brightness`
3. Write `wingspan.service` unit file under `/etc/systemd/system/`, enable + start.
4. Plug the inline USB power meter between the bench supply and the Pi; let it run for ≥ 30 min.

**Done when:** logged average draw is ≤ 100 mA, service auto-restarts after `kill -9`, BLE still advertises as `wingSpan-1`.

---

## Session 2 — CSV logging + app sync (~3–4 h)

**Goal:** Pi writes one row per minute to disk; phone can download and clear the log.

Tasks:
1. `csv_writer.py` module: appends to `/var/lib/wingspan/log.csv`, line-buffered, rotates oldest 10 % when file exceeds 200 MB.
2. Row schema: `ts,t,h,w,db,bv,bp,chg,hum,workers,queen,swarm,events`
   (timestamp, temp, humidity, weight, sound dB, battery V, battery %, charging bool, four band dBs, comma-joined events).
3. Add new BLE characteristics on the existing service:
   - `DOWNLOAD_UUID` (notify): on subscribe, Pi chunks the CSV file in MTU-sized notifications; ends with a zero-length packet as EOF marker.
   - Extend `CMD_UUID` writes:
     - `0x01` zero weight (existing)
     - `0x02` clear log
     - `0x03 <8 bytes>` sync time — interpret 8-byte big-endian Unix epoch
4. App (`index.html`):
   - On connect, auto-write `0x03 <epoch>` to sync time.
   - **Download CSV** button: subscribe to `DOWNLOAD_UUID`, collect chunks until EOF, save as a Blob to phone Downloads, show progress.
   - **Clear log** button: writes `0x02` after a confirm dialog.
   - Display battery % and charging icon in the existing weight card neighborhood.
5. Integrate MAX17048: read voltage / SoC / charge-rate on each cycle; include in payload.

**Done when:** download a 1-day CSV to the phone, clear it, see the log restart from empty on next minute.

---

## Session 3 — First production unit build (~3 h)

**Goal:** unit 1 assembled, soak-tested 6 h on battery alone.

Connections (mostly screw terminals and JST plugs):
1. LiPo → BQ24074 `BAT`
2. Solar panel → BQ24074 `IN` (confirm Voc ≤ 10 V)
3. BQ24074 `SYS` → S13V30F5 `VIN` / `GND`
4. S13V30F5 `5V` → Pi 5 V (GPIO pin 2) and `GND` (pin 6)
5. STEMMA QT chain: Pi (#5985 adapter or soldered I²C) → SHT40 → MAX17048
6. BQ24074 `PG` → Pi GPIO (e.g. GPIO17), 10 kΩ pull-up
7. USB mic → Pi USB port

Verify:
- Power-on with battery only: BLE advertises, log file growing.
- Pull solar input: still runs.
- Charge cycle visible in MAX17048 charge-rate reading.

**Done when:** unit runs ≥ 6 h on battery only, the next-morning CSV has the expected number of rows, and the phone can download + clear it.

---

## Session 4 — Replicate units 2–5 + I²S mic swap (~3–4 h)

**Goal:** 4 more units built; at least one configured with SPH0645 I²S mic.

Tasks:
1. Image microSD cards from a known-good unit-1 snapshot (`dd` or Pi Imager custom image). Set each Pi's hostname and the wingSpan unit number (`wingSpan-2` … `wingSpan-5`) before first boot.
2. Build each unit to the unit-1 recipe.
3. For one unit, swap to SPH0645:
   - Solder 5 wires (3V3, GND, BCLK, LRCL, DOUT; SEL → GND for left channel).
   - Add `dtparam=i2s=on` and `dtoverlay=googlevoicehat-soundcard` to `/boot/firmware/config.txt`.
   - Set `MIC = "i2s"` in `sensor_ble.py`.
   - Verify with `arecord -l` and the existing `test_audio.py`.
4. Each unit gets a 1-hour bench burn-in before deployment.

**Done when:** all 5 units boot, advertise distinct names, log to local CSV, and pass a 1 h burn-in.

---

## Session 5 — Deploy + verify in hives (~2–3 h)

**Goal:** units installed, last-mile verification per hive.

For each hive:
1. Mount unit; route solar panel facing south, not shaded by lid.
2. Walk up, connect via app, confirm:
   - Live values look sensible (temp matches outside conditions during install).
   - Time syncs.
   - Battery % present and increasing if sun is on the panel.
   - Sample CSV downloads.
   - Clear log so each hive starts deployment from row 1.
3. Note hive name ↔ unit number mapping (write on the unit and in your phone notes).
4. Schedule a weekly visit: download CSV, clear, replace anything dead.

**Done when:** all 5 hives report from their respective units; you have a CSV file per hive saved on your phone with rows from the first deployment hour.

---

## Out of scope for this plan

Tagged for separate tracks once the above is working:

- **Weatherproof enclosure**: critical for real outdoor deployment but orthogonal to firmware. Spec after Session 3, build in parallel with Session 4.
- **Cloud aggregation / multi-hive dashboard**: defer until weekly walk-the-yard gets old.
- **On-device ML classification (YAMNet / custom CNN)**: defer until you have weeks of recordings to train against. Hooks into `analyze()` when ready.
- **Real load cell for weight**: replace the static `12.345 kg` placeholder. HX711 + 4× strain-gauge bars under the hive. Reuse the existing zero-command path.
- **OTA firmware updates**: until then, swap SD cards or `git pull` over a bench Wi-Fi.

---

## Risks worth naming before Session 1

1. **No RTC means timestamp gaps after a field reboot.** Mitigated by phone sync + interpolation, but if a unit reboots and no one connects for days, those rows are unrecoverable in wall-clock terms. Acceptable; flag if it bites.
2. **Pi Zero 2 W can't deep-sleep.** If battery life is unacceptable after Session 1 measurements (target ≥ 48 h dark, indefinite with sun), the right move is an MCU sidekick, not more Pi-side tuning.
3. **BLE-only download means you must be on-site.** No remote access. Acceptable for v1; revisit at "cloud aggregation" track.
4. **Bees and condensation.** Without an enclosure plan, plan to lose units to moisture or propolis. Don't deploy Session 5 until Session 3's enclosure decision is made.
