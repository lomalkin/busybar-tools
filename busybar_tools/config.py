from importlib.metadata import version

PROJECT_NAME = "busybar_tools"

try:
    PACKAGE_VERSION = version("busybar-tools")
except Exception:
    PACKAGE_VERSION = "unknown"

# Network:
# UPDATE_SERVER_BASE = "https://update.flipperzero.one/builds/busybar-firmware/"
UPDATE_SERVER_BASE = "https://update.busy.app/builds/busybar-firmware/"
UPDATE_DEFAULT_BRANCH = "dev"
UPDATE_DIRECTORY_URL = "https://update.busy.app/busybar-firmware/directory.json"

FETCH_TIMEOUT_DEFAULT = 60  # seconds
TCP_TIMEOUT_DEFAULT = 5  # seconds

# Destructive commands (write-recovery, recover, factory-reset) give the user
# this Ctrl+C window before acting.
CONFIRM_TIMEOUT_DEFAULT = 3  # seconds

# Recovery over USB DFU:
RECOVERY_SOURCE_DEFAULT = "dev"
DFU_WAIT_TIMEOUT_DEFAULT = 30  # seconds to wait for a DFU USB device to appear
RECOVERY_WAIT_TIMEOUT_DEFAULT = 120  # seconds to wait for the device to come back after flashing

# Factory reset:
FACTORY_RESET_OFFLINE_TIMEOUT_DEFAULT = 180  # seconds to wait for the device to drop offline

# HTTP User-Agent for update-server requests. The default urllib UA ("Python-urllib/x.y")
# is blocked (403) by the update mirror's CDN/WAF, so a non-default UA is required.
HTTP_USER_AGENT = f"busybar-tools/{PACKAGE_VERSION}"

# Device:
DEVICE_IP = "10.0.4.20"
DEVICE_IP_REF = "10.0.5.20" # misc
DEVICE_PORT = 23

# Firmware U5 target:
U5_TARGET_HW = 22   # Default, can be overridden by -t / --target option (any integer accepted).

# Device Paths:
DIR_BSB_TMP = "/ext/tmp"
DIR_BSB_TMP_UPDATE = "/ext/tmp/update"
DIR_BSB_RECOVERY = "/bkp/recovery"
UPDATE_MANIFEST_FILE = "update.json"
