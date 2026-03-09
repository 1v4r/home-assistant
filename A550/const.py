from __future__ import annotations

from datetime import timedelta

DOMAIN = "a550"
PLATFORMS = ["sensor", "select"]

CONF_ADDRESS = "address"
CONF_NAME = "name"

SERVICE_UUID = "00006301-0000-0041-4c50-574953450000"
DATA_CHAR_UUID = "00006302-0000-0041-4c50-574953450000"
CTRL_CHAR_UUID = "00006303-0000-0041-4c50-574953450000"

DEFAULT_POLL_INTERVAL = timedelta(seconds=30)
BLE_PACKET_TIMEOUT = 3.0
BLE_PROBE_TIMEOUT = 1.0
BLE_CONNECT_TIMEOUT = 10.0

# A550 seems to report probe temperatures in Fahrenheit on many units.
# Set this to False if your device is configured to send Celsius directly.
ASSUME_FAHRENHEIT = True

PROBE_COUNT = 2

COOKING_STATUS_OPTIONS = {
    0: "started",
    1: "paused",
    2: "stopped",
    3: "alarming",
    4: "done",
}

SETTABLE_COOKING_STATUS = {
    "started": 0,
    "paused": 1,
    "stopped": 2,
}
