import logging
import time

from busybar_tools.device.cli import BusybarCli
from busybar_tools.errors import DeviceError, DeviceProtocolError
from busybar_tools.options import DeviceEndpoint

VERSION_FIELDS = (
    "u5_firmware_branch", "u5_firmware_commit", "u5_firmware_builddate",
    "sl_firmware_branch", "sl_firmware_commit", "sl_firmware_builddate",
)
DETECT_FIELDS = ("u5_firmware_target", "sl_nwp_signature", "sl_m4_signature")


def device_info_ready(info, required_keys):
    return all(info.get(key) for key in required_keys)


def read_device_info(endpoint: DeviceEndpoint, retries=1, delay=1, required_keys=None):
    last_info = None
    last_error = None
    for attempt in range(retries):
        try:
            with BusybarCli(endpoint.address) as cli:
                info = cli.device_info()
            last_info = info
            if not required_keys or device_info_ready(info, required_keys):
                return info
            missing = [key for key in required_keys if not info.get(key)]
            logging.debug("device_info incomplete (missing %s), attempt %s/%s", missing, attempt + 1, retries)
        except Exception as exc:
            last_error = exc
            logging.debug("device_info attempt %s/%s failed: %s", attempt + 1, retries, exc)
        if attempt + 1 < retries:
            time.sleep(delay)
    if last_info is not None:
        logging.warning("device_info still incomplete after retries; reporting partial data.")
        return last_info
    raise DeviceError(f"Failed to read device_info from {endpoint.host}:{endpoint.port}: {last_error}")


def _device_info_bool(info, key):
    value = info.get(key)
    if value is None:
        raise DeviceProtocolError(f"device_info is missing '{key}'")
    return str(value).strip().lower() == "true"


def device_info_target(info):
    try:
        return int(info["u5_firmware_target"])
    except (KeyError, ValueError) as exc:
        raise DeviceProtocolError(
            "Could not read hardware target (u5_firmware_target) from device_info"
        ) from exc


def device_info_signed(info):
    nwp = _device_info_bool(info, "sl_nwp_signature")
    m4 = _device_info_bool(info, "sl_m4_signature")
    if nwp != m4:
        raise DeviceProtocolError(
            f"Inconsistent secure boot state (sl_nwp_signature={nwp}, sl_m4_signature={m4}); "
            "cannot decide signed/unsigned automatically."
        )
    return nwp


def device_version_fingerprint(info):
    return tuple(info.get(key, "?") for key in VERSION_FIELDS)


def format_version(info):
    return (
        f"u5 {info.get('u5_firmware_branch', '?')}@{info.get('u5_firmware_commit', '?')} "
        f"({info.get('u5_firmware_builddate', '?')}), "
        f"sl {info.get('sl_firmware_branch', '?')}@{info.get('sl_firmware_commit', '?')} "
        f"({info.get('sl_firmware_builddate', '?')})"
    )

