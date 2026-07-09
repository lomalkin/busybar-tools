import logging
import time

from busybar_tools.bsb_lite import BSB_Lite
from busybar_tools.config import UPDATE_MANIFEST_FILE
from busybar_tools.helpers import print_pretty, wait_for_device


def wait_for_device_maybe(args):
    """Wait for the device to be reachable, unless --no-wait was passed."""
    if getattr(args, "no_wait", False):
        logging.info("Skipping device reachability check (--no-wait).")
        return
    wait_for_device(args.device, verbose=getattr(args, "verbose", True))


def bsb_sysctl_debug_enable(device, port):
    logging.info("Try to enable debug mode...")

    try:
        bsb = BSB_Lite((device, port))
        bsb.start()
        res = bsb.sysctl_debug(1)
        print_pretty(res)
        return True
    except Exception as e:
        logging.error(f"Failed to enable debug mode: {e}")
        return False


def bsb_invoke_update(device, port, file_path):
    logging.info("Try to invoke update via API...")

    try:
        bsb = BSB_Lite((device, port))
        bsb.start()
        res = bsb.cmd_oneshot(f"update install {file_path}/{UPDATE_MANIFEST_FILE}", timeout=3)
        print_pretty(res)
        return True
    except Exception as e:
        logging.error(f"Failed to invoke update: {e}")
        return False


def _device_info_ready(info, required_keys):
    """True if all required device_info keys are present and non-empty."""
    return all(info.get(k) for k in required_keys)


def device_read_info(device, port, retries=1, delay=1, required_keys=None):
    """Connect to the device CLI and return the parsed device_info dict."""
    last_info = None
    last_err = None
    for attempt in range(retries):
        try:
            with BSB_Lite((device, port)) as bsb:
                info = bsb.device_info()
            last_info = info
            if not required_keys or _device_info_ready(info, required_keys):
                return info
            missing = [k for k in required_keys if not info.get(k)]
            logging.debug(f"device_info incomplete (missing {missing}), attempt {attempt + 1}/{retries}")
        except Exception as e:
            last_err = e
            logging.debug(f"device_info attempt {attempt + 1}/{retries} failed: {e}")
        if attempt + 1 < retries:
            time.sleep(delay)

    if last_info is not None:
        if required_keys and not _device_info_ready(last_info, required_keys):
            logging.warning("device_info still incomplete after retries; reporting partial data.")
        return last_info
    raise RuntimeError(f"Failed to read device_info from {device}:{port}: {last_err}")


def _device_info_bool(info, key):
    val = info.get(key)
    if val is None:
        raise RuntimeError(f"device_info is missing '{key}'")
    return str(val).strip().lower() == "true"


def device_info_target(info):
    """Hardware target reported by the device."""
    try:
        return int(info["u5_firmware_target"])
    except (KeyError, ValueError):
        raise RuntimeError("Could not read hardware target (u5_firmware_target) from device_info")


def device_info_signed(info):
    """Whether the device runs signed firmware."""
    nwp = _device_info_bool(info, "sl_nwp_signature")
    m4 = _device_info_bool(info, "sl_m4_signature")
    if nwp != m4:
        raise RuntimeError(
            f"Inconsistent secure boot state (sl_nwp_signature={nwp}, sl_m4_signature={m4}); "
            "cannot decide signed/unsigned automatically."
        )
    return nwp


_VERSION_FIELDS = (
    "u5_firmware_branch", "u5_firmware_commit", "u5_firmware_builddate",
    "sl_firmware_branch", "sl_firmware_commit", "sl_firmware_builddate",
)

_DETECT_FIELDS = ("u5_firmware_target", "sl_nwp_signature", "sl_m4_signature")


def device_version_fingerprint(info):
    """Tuple of version-identifying fields, for before/after comparison."""
    return tuple(info.get(k, "?") for k in _VERSION_FIELDS)


def format_version(info):
    """Human-readable firmware version string from device_info."""
    return (
        f"u5 {info.get('u5_firmware_branch', '?')}@{info.get('u5_firmware_commit', '?')} "
        f"({info.get('u5_firmware_builddate', '?')}), "
        f"sl {info.get('sl_firmware_branch', '?')}@{info.get('sl_firmware_commit', '?')} "
        f"({info.get('sl_firmware_builddate', '?')})"
    )

