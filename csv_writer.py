"""CSV logger for wingSpan. One row per minute appended to
/var/lib/wingspan/log.csv. When the file exceeds CAP_MB, the oldest
10% of data rows are dropped (header preserved). Streaming rotation
keeps memory bounded — the file is never fully loaded.

Thread-safe: callers can hit append() from any thread."""

import csv
import os
import threading

LOG_PATH             = "/var/lib/wingspan/log.csv"
CAP_MB               = 200
ROTATE_DROP_FRACTION = 0.10

HEADER = [
    "ts", "t", "h", "w", "db",
    "bv", "bp", "chg",
    "hum", "workers", "queen", "swarm",
    "events",
]

_lock = threading.Lock()
_file = None


def _open() -> None:
    global _file
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    new_file = not os.path.exists(LOG_PATH) or os.path.getsize(LOG_PATH) == 0
    _file = open(LOG_PATH, "a", buffering=1, newline="")
    if new_file:
        csv.writer(_file).writerow(HEADER)


def append(row) -> None:
    with _lock:
        if _file is None:
            _open()
        csv.writer(_file).writerow(row)
        try:
            size = os.path.getsize(LOG_PATH)
        except OSError:
            return
        if size > CAP_MB * 1024 * 1024:
            _rotate_locked()


def _rotate_locked() -> None:
    global _file
    _file.close()
    _file = None

    with open(LOG_PATH, "r", newline="") as f:
        total_rows = sum(1 for _ in f) - 1
    if total_rows <= 0:
        _open()
        return
    drop_n = max(1, int(total_rows * ROTATE_DROP_FRACTION))

    tmp = LOG_PATH + ".tmp"
    with open(LOG_PATH, "r", newline="") as src, open(tmp, "w", newline="") as dst:
        dst.write(src.readline())  # header
        for _ in range(drop_n):
            src.readline()
        while True:
            chunk = src.read(1 << 20)
            if not chunk:
                break
            dst.write(chunk)
    os.replace(tmp, LOG_PATH)
    _open()
