# wingSpan hive sensor — recipient guide

You've received a Raspberry Pi running an acoustic sensor near a beehive. Every 2 minutes it records a 5-second audio clip; every minute it appends a row of temperature / humidity / sound-level data to a CSV log. Your job is to pull those files to your laptop and analyze the audio.

This guide walks you through one-time setup (~10 min) and the day-to-day commands you'll run.

---

## What's in the box

- Raspberry Pi with an I²S MEMS microphone attached
- Power supply (USB-C)

The Pi is pre-configured to auto-join your WiFi network `wjm` on boot.

---

## One-time setup

### 1. Plug the Pi in

Connect the USB-C power. After ~30 seconds it will boot, join `wjm` WiFi, and start recording. No keyboard or monitor needed.

### 2. Create a Tailscale account

[Tailscale](https://tailscale.com) is a private mesh-VPN service we use to connect your laptop to the Pi from anywhere — no port-forwarding, no public IP, no exposure to the open internet. It's free for personal use.

1. Go to https://login.tailscale.com/start
2. Sign up with Google, Microsoft, GitHub, or email
3. Note the email you used — you'll need to send it to William so he can share the Pi with your account

### 3. Accept the device share

William will send you an invitation link from his Tailscale admin console. Click it (while logged into your Tailscale account in the same browser) and accept. The Pi (`raspberrypi`) will then appear in your machines list at https://login.tailscale.com/admin/machines.

### 4. Install Tailscale on your laptop

- **macOS:** download from https://tailscale.com/download/macos or run `brew install --cask tailscale-app`
- **Windows:** download the installer from https://tailscale.com/download/windows
- **Linux:** `curl -fsSL https://tailscale.com/install.sh | sh`

After install, sign in with the same Tailscale account. The Pi should show up in your machine list and be reachable as `raspberrypi`.

### 5. (Recommended) Send William your SSH public key

If you do this **before the unit ships**, you won't have to type the Pi password every time you connect.

Generate a key on your laptop (skip if you already have `~/.ssh/id_ed25519.pub`):

```
ssh-keygen -t ed25519 -C "your-name@example.com"
```

Press Enter through all prompts to accept defaults. Then print the public key and send the output to William:

```
cat ~/.ssh/id_ed25519.pub
```

He'll add it to the Pi before shipping. After that, `ssh beehaus@raspberrypi` will connect without prompting for a password.

If you skip this step you can still use the Pi password — it just means typing it every time.

### 6. First SSH connection

In a terminal on your laptop:

```
ssh beehaus@raspberrypi
```

If you sent your SSH key in step 5, it connects immediately. Otherwise, type the Pi password (William will send this separately). Confirm `yes` to the host fingerprint on the first connection. You should see a `beehaus@raspberrypi:~ $` prompt. Type `exit` to disconnect.

---

## Pulling data

All commands are run on **your laptop**, not on the Pi.

### Audio files

WAV files live at `/var/lib/wingspan/audio/YYYY-MM-DD/HH-MM-SSZ.wav` (timestamps are UTC). Each is a 5-second mono recording at 48 kHz, ~480 KB.

Pull everything to a local folder:

```
mkdir -p ~/wingspan-data/audio
scp -r beehaus@raspberrypi:/var/lib/wingspan/audio/ ~/wingspan-data/audio/
```

Pull just one day:

```
scp -r beehaus@raspberrypi:/var/lib/wingspan/audio/2026-06-23/ ~/wingspan-data/audio/
```

For ongoing transfers, `rsync` is faster (only pulls new files):

```
rsync -av beehaus@raspberrypi:/var/lib/wingspan/audio/ ~/wingspan-data/audio/
```

### CSV log

One row per minute. Columns: `ts, t, h, w, db, bv, bp, chg, hum, workers, queen, swarm, events` (timestamp, temp °C, humidity %, weight kg [see note below], overall dBFS, battery cols [empty for now], four band powers in dB, comma-separated event labels).

### Note on the weight column (`w`) — WIP

You will see a static value (currently `12.345`) in the `w` column. **The real weight system is not active yet.**

The plan is for the hive to sit on four legs, each with its own strain-gauge load cell. Before the readings mean anything, each leg has to be **individually calibrated** against the Pi (place a known weight on each leg, capture the raw reading, compute the per-leg conversion coefficient). The four calibrated leg readings will then be summed each minute and written to the `w` column.

Until that calibration step is wired up and done, the `w` column is a placeholder — please ignore it for now. Audio, temperature, and humidity are the real signals from this unit.

```
scp beehaus@raspberrypi:/var/lib/wingspan/log.csv ~/wingspan-data/log.csv
```

### How often to pull

The Pi holds **~9 days** of audio before the oldest files get auto-deleted. **Pull at least once a week.** CSV holds much longer (~3.8 years at the current cadence).

---

---

## Live readings via Bluetooth (optional)

The Pi also advertises itself as a Bluetooth Low Energy peripheral named `wingSpan-N`, where `N` is the unit number printed on the device (your shipment-specific README will tell you which number you have). If you stand within ~10 m of the unit you can open a small web page in Chrome and see live temperature, humidity, sound level, and band activity updating about once a second. This is handy for sanity-checking the unit when you're physically near the hive — confirming the mic is hearing something, the temperature looks right, etc.

This is **optional**. All the data you need for analysis is in the WAV files and CSV log you pull over Tailscale. Use Bluetooth only if you want a live readout.

### Requirements

- **Chrome on Android, macOS, Windows, or Linux** (or Chromium / Edge)
- **Not supported:** Safari, Firefox, or anything on iPhone/iPad (Apple does not allow Web Bluetooth)
- Bluetooth turned on
- Within ~10 m of the unit

### How to use it

1. William will send you a file called `index.html`. Save it anywhere on your device.
2. Open it in Chrome (double-click on macOS/Windows; on Android, save it to your Downloads folder and tap to open with Chrome).
3. Click the **Connect** button.
4. A browser pop-up will list nearby Bluetooth devices — pick the one matching your unit's name (e.g. **wingSpan-1**).
5. The page will start showing live readings updating each second.

You can leave the page open as long as the device stays in range. If you walk out of range or disconnect, click **Reconnect** to resume.

### What the readings mean

- **Temperature / Humidity** — current values from the on-board sensor.
- **Sound level (dBFS)** — overall volume of the most recent 5-second audio capture. Quiet rooms read around -70 dBFS; a normal speaking voice nearby reads around -25 dBFS.
- **Bee activity** — labels light up when one of the bee bands (workers, queen, swarm) is significantly louder than the resting hum band. Empty if nothing is detected.
- **Bands** — raw dB power in each of the four frequency bands.
- **Hive weight** — placeholder for now, see the WIP note above. Ignore until the load cells are calibrated.

### The "Zero weight" button

This button is wired up but doesn't do anything useful yet — the weight system is still WIP. Pressing it just resets the placeholder value to zero.

---

## Analysis suggestions

Each WAV is 5 s of 16-bit mono PCM at 48 kHz. Any standard audio tool will work:

- **Audacity** (free, GUI) — drag in a WAV, switch to spectrogram view (Track menu → Spectrogram)
- **Sonic Visualiser** (free, GUI) — better for batch spectrogram inspection
- **librosa** (Python) — `librosa.load()` then `librosa.stft()` for programmatic frequency analysis
- **sox** (CLI) — `sox file.wav -n stat` and `sox file.wav -n spectrogram` for quick checks

The bands of interest for bee acoustics:

| Band | Range | Meaning |
|---|---|---|
| hum | 100–150 Hz | resting colony baseline |
| workers | 200–270 Hz | flight, general activity, waggle dance |
| queen | 320–450 Hz | queen tooting/quacking |
| swarm | 400–500 Hz | swarming behavior |

---

## Troubleshooting

### `ssh: Could not resolve hostname raspberrypi`

Tailscale isn't running or the Pi isn't online. Check:
1. Tailscale app on your laptop is signed in and showing connected
2. The Pi shows online (green dot) at https://login.tailscale.com/admin/machines
3. If the Pi is offline, it usually means it lost power or WiFi — check the unit physically

### Connection times out

Same as above — Pi is offline. Power-cycle the unit if needed; it will auto-reconnect.

### `Permission denied (publickey,password)`

Wrong password. Double-check with William.

### No new files

```
ssh beehaus@raspberrypi 'systemctl status wingspan.service'
```

Should show `active (running)`. If not:

```
ssh beehaus@raspberrypi 'sudo systemctl restart wingspan.service'
```

### Disk full warnings

The Pi rotates oldest audio automatically at 3 GB. If you somehow filled the SD card with something else, check with:

```
ssh beehaus@raspberrypi 'df -h /'
```

---

## Contact

Questions or weirdness — text William.
