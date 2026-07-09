import logging
import time

from busybar_tools.config import DEVICE_PORT
from busybar_tools.dfu.backends import PyUsbDfuSeBackend, ensure_dfu_util


def ensure_recovery_backend(name="pyusb", dfu_util_executable=None, auto_install_dfu_util=True):
    name = (name or "pyusb").lower()
    if name == "pyusb":
        backend = PyUsbDfuSeBackend()
        if backend.is_available():
            return backend
        raise RuntimeError("PyUSB backend is not available. Install pyusb/libusb or use `--backend dfu-util`.")

    if name == "dfu-util":
        return ensure_dfu_util(dfu_util_executable, auto_install=auto_install_dfu_util)

    if name == "auto":
        backend = PyUsbDfuSeBackend()
        if backend.is_available():
            return backend
        logging.warning("PyUSB backend is not available; falling back to dfu-util.")
        return ensure_dfu_util(dfu_util_executable, auto_install=auto_install_dfu_util)

    raise RuntimeError(f"Unknown recovery backend '{name}'. Expected: pyusb, dfu-util, auto.")


def wait_for_dfu_device(backend, timeout=30, delay=1):
    deadline = time.time() + timeout
    while time.time() <= deadline:
        if backend.find_devices():
            return True
        time.sleep(delay)
    return False


def enter_dfu_via_cli(device, port=DEVICE_PORT):
    from busybar_tools.bsb_lite import BSB_Lite

    with BSB_Lite((device, port)) as bsb:
        bsb.cmd_oneshot("power boot u5", timeout=1)
