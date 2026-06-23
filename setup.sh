#!/usr/bin/env bash
# wingSpan Pi setup script — provisions a fresh Raspberry Pi OS Lite install.
#
# Usage:
#   ssh beehaus@raspberrypi
#   curl -fsSL https://raw.githubusercontent.com/Bgoat/pi-ble-sensor/main/setup.sh | bash
#
# For unit numbers other than 1:
#   curl -fsSL https://raw.githubusercontent.com/Bgoat/pi-ble-sensor/main/setup.sh \
#     | UNIT_NUMBER=2 TARGET_HOSTNAME=wingspan-2 bash
#
# After this script: `sudo tailscale up`, then `sudo reboot`.

set -euo pipefail

# ---- Configuration (override via env vars) ----
UNIT_NUMBER="${UNIT_NUMBER:-1}"
TARGET_HOSTNAME="${TARGET_HOSTNAME:-raspberrypi}"
WJM_PSK="${WJM_PSK:-intelplay}"
REPO_URL="https://github.com/Bgoat/pi-ble-sensor.git"

BLE_NAME="wingSpan-${UNIT_NUMBER}"
PI_USER="$(id -un)"
PI_HOME="$(getent passwd "$PI_USER" | cut -d: -f6)"

if [ "$PI_USER" = "root" ]; then
    echo "Run this script as a regular user (e.g. beehaus), not root." >&2
    exit 1
fi

echo "================================================================"
echo "wingSpan setup"
echo "  Unit BLE name: ${BLE_NAME}"
echo "  Hostname:      ${TARGET_HOSTNAME}"
echo "  User:          ${PI_USER}"
echo "  Home:          ${PI_HOME}"
echo "================================================================"

# ---- 1. System packages ----
echo
echo "[1/12] System packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3-dbus python3-gi python3-numpy python3-pip \
    libportaudio2 git i2c-tools curl rfkill >/dev/null

# ---- 2. Python packages ----
# sounddevice was dropped from Debian Trixie's apt repos — install via pip.
echo "[2/12] Python packages"
pip3 install --break-system-packages --quiet \
    sounddevice bluezero adafruit-circuitpython-sht4x adafruit-blinka

# ---- 3. Enable I2C + I2S in /boot/firmware/config.txt ----
echo "[3/12] Firmware config (I2C, I2S, googlevoicehat overlay)"
CONFIG=/boot/firmware/config.txt
sudo raspi-config nonint do_i2c 0  # 0 = enable

if grep -q "^#dtparam=i2s=on" "$CONFIG"; then
    sudo sed -i 's/^#dtparam=i2s=on/dtparam=i2s=on/' "$CONFIG"
elif ! grep -q "^dtparam=i2s=on" "$CONFIG"; then
    echo "dtparam=i2s=on" | sudo tee -a "$CONFIG" >/dev/null
fi

if ! grep -q "dtoverlay=googlevoicehat-soundcard" "$CONFIG"; then
    echo "dtoverlay=googlevoicehat-soundcard" | sudo tee -a "$CONFIG" >/dev/null
fi

# ---- 4. Clone or update the repo ----
echo "[4/12] Cloning / updating wingspan repo"
cd "$PI_HOME"
if [ -d pi-ble-sensor/.git ]; then
    cd pi-ble-sensor
    git fetch --quiet origin
    git reset --quiet --hard origin/main
else
    git clone --quiet "$REPO_URL" pi-ble-sensor
    cd pi-ble-sensor
fi

# ---- 5. Stage Python + boot script in $HOME ----
echo "[5/12] Staging firmware files in ${PI_HOME}"
cp sensor_ble.py csv_writer.py wingspan-boot.sh "$PI_HOME/"
chmod +x "$PI_HOME/wingspan-boot.sh"

# Personalize the BLE LocalName
sed -i 's/local_name="wingSpan-1"/local_name="'"${BLE_NAME}"'"/' "$PI_HOME/sensor_ble.py"

# ---- 6. systemd unit ----
echo "[6/12] Installing wingspan.service"
sudo install -m 644 wingspan.service /etc/systemd/system/wingspan.service
sudo systemctl daemon-reload

# ---- 7. Data directory ----
echo "[7/12] Creating /var/lib/wingspan"
sudo install -d -o "$PI_USER" -g "$PI_USER" /var/lib/wingspan /var/lib/wingspan/audio

# ---- 8. Tailscale ----
if ! command -v tailscale >/dev/null 2>&1; then
    echo "[8/12] Installing Tailscale"
    curl -fsSL https://tailscale.com/install.sh | sh >/dev/null
else
    echo "[8/12] Tailscale already installed"
fi

# ---- 9. WiFi profiles: bump existing to priority 10, add wjm at priority 0 ----
echo "[9/12] Configuring WiFi profiles"
nmcli -t -f NAME,TYPE connection show \
  | awk -F: '$2=="802-11-wireless" && $1!="wjm" {print $1}' \
  | while read -r name; do
        sudo nmcli connection modify "$name" connection.autoconnect-priority 10
    done

if ! nmcli -t -f NAME connection show | grep -qx wjm; then
    sudo nmcli connection add type wifi con-name wjm ifname wlan0 ssid wjm \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$WJM_PSK" \
        autoconnect yes connection.autoconnect-priority 0 >/dev/null
fi

# ---- 10. Bluetooth controller alias (Chrome shows this, not the LocalName) ----
# Also disable the discoverable timeout so the BLE peripheral stays visible
# to scanners. wingspan-boot.sh sets discoverable=on at each service start.
echo "[10/12] Setting Bluetooth alias to ${BLE_NAME} and disabling discoverable timeout"
sudo bluetoothctl -- system-alias "${BLE_NAME}" >/dev/null
sudo sed -i 's/^#DiscoverableTimeout = .*/DiscoverableTimeout = 0/' /etc/bluetooth/main.conf
if ! grep -q "^DiscoverableTimeout = 0" /etc/bluetooth/main.conf; then
    sudo sed -i 's/^DiscoverableTimeout = .*/DiscoverableTimeout = 0/' /etc/bluetooth/main.conf
fi

# ---- 11. Hostname ----
if [ "$(hostname)" != "$TARGET_HOSTNAME" ]; then
    echo "[11/12] Setting hostname to ${TARGET_HOSTNAME}"
    sudo hostnamectl set-hostname "$TARGET_HOSTNAME"
else
    echo "[11/12] Hostname already ${TARGET_HOSTNAME}"
fi

# ---- 12. Disable lightdm (if installed — Lite usually doesn't have it) ----
if systemctl list-unit-files lightdm.service >/dev/null 2>&1; then
    if [ "$(systemctl is-enabled lightdm.service 2>/dev/null || true)" = "enabled" ]; then
        echo "[12/12] Disabling lightdm.service"
        sudo systemctl disable lightdm.service >/dev/null 2>&1 || true
    else
        echo "[12/12] lightdm not enabled, skipping"
    fi
else
    echo "[12/12] lightdm not installed (good — Lite image)"
fi

sudo systemctl enable wingspan.service >/dev/null

echo
echo "================================================================"
echo "Setup complete."
echo
echo "Next steps:"
echo
echo "  1. Authorize Tailscale (interactive — opens a URL):"
echo "       sudo tailscale up"
echo
echo "  2. Reboot to load the I2S audio overlay:"
echo "       sudo reboot"
echo
echo "  3. After reboot, verify:"
echo "       systemctl is-active wingspan      # should print 'active'"
echo "       tail /var/lib/wingspan/log.csv    # CSV rows appearing"
echo "================================================================"
