"""Fixtures and config for live-device (hardware) tests.

Edit the constants below to tune the flashing tests.
"""
import os
import time
import types

import pytest

import busybar_tools as bt
from busybar_tools.bsb_lite import BSB_Lite
from busybar_tools.helpers import network_ping_bool, wait_for_device

# --- test config (edit here) ------------------------------------------------
# write-recovery always flashes this pinned, known-good recovery image.
WRITE_RECOVERY_VERSION = "0.10.2"
# Source for install / auto-install flash tests. None => default branch
FLASH_SOURCE = None
# Generous bounds for reflash/reboot (minutes) — we just wait, no short timeouts.
REBOOT_OFFLINE_TIMEOUT = 180   # seconds to allow the device to drop offline
POST_REBOOT_READ_RETRIES = 30  # device_read_info attempts after it comes back
# ----------------------------------------------------------------------------

_READY_KEYS = bt._VERSION_FIELDS + bt._DETECT_FIELDS


@pytest.fixture(scope="session")
def device_host(pytestconfig):
    return pytestconfig.getoption("--device")


@pytest.fixture(scope="session")
def device_port(pytestconfig):
    return pytestconfig.getoption("--port")


@pytest.fixture(scope="session")
def live_device(device_host, device_port):
    """Skip the hardware test if the device is not reachable."""
    if not network_ping_bool(device_host, timeout=2):
        pytest.skip(f"device {device_host} is not reachable")
    return device_host, device_port


@pytest.fixture(scope="session")
def device_info_live(live_device):
    host, port = live_device
    return bt.device_read_info(host, port, retries=10, delay=2, required_keys=_READY_KEYS)


@pytest.fixture
def autodetect(device_info_live):
    """Autodetected target/signing + current branch, as the device reports them."""
    return {
        "target": bt.device_info_target(device_info_live),
        "signed": bt.device_info_signed(device_info_live),
        "branch": device_info_live["u5_firmware_branch"],
    }


@pytest.fixture
def flash_source(autodetect):
    return FLASH_SOURCE or autodetect["branch"]


@pytest.fixture
def recovery_version():
    return WRITE_RECOVERY_VERSION


@pytest.fixture
def make_args(live_device):
    """Factory for an args namespace; pass per-command fields as kwargs."""
    host, port = live_device

    def _make(**over):
        base = dict(device=host, port=port, verbose=True, no_wait=True)
        base.update(over)
        return types.SimpleNamespace(**base)

    return _make


@pytest.fixture
def wait_until_back(live_device):
    """Wait through a reboot: offline (bounded) -> online (unbounded) -> read full device_info."""
    host, port = live_device

    def _wait():
        wait_for_device(host, timeout=REBOOT_OFFLINE_TIMEOUT, verbose=True, success_ping_as=False)
        wait_for_device(host, verbose=True)  # no timeout: just wait until reachable
        return bt.device_read_info(host, port, retries=POST_REBOOT_READ_RETRIES, delay=2, required_keys=_READY_KEYS)

    return _wait


@pytest.fixture
def device_cleanup(make_args):
    """Best-effort removal of an on-device path (for test teardown)."""
    def _rm(path):
        try:
            bt.run_storage(make_args(verbose=False, storage_args=["--", "remove", path]))
        except Exception:
            pass

    return _rm


@pytest.fixture(scope="session")
def prefetched_bundle(live_device, device_info_live, tmp_path_factory):
    """Download a bundle once (file + unpacked dir) for install-from-file/dir tests."""
    target = bt.device_info_target(device_info_live)
    signed = bt.device_info_signed(device_info_live)
    branch = device_info_live["u5_firmware_branch"]
    base = dict(source=branch, target=target, signed=signed, update_bundle_type="update")

    file_dir = tmp_path_factory.mktemp("bundle_file")
    bt.run_fetch(types.SimpleNamespace(**base, unpack=False, output=str(file_dir) + os.sep))
    bundle_file = next(p for p in file_dir.iterdir() if p.is_file())

    unpack_dir = tmp_path_factory.mktemp("bundle_unpacked")
    bt.run_fetch(types.SimpleNamespace(**base, unpack=True, output=str(unpack_dir)))

    return types.SimpleNamespace(file=str(bundle_file), dir=str(unpack_dir),
                                 target=target, signed=signed, branch=branch)


@pytest.fixture
def factory_reset(live_device):
    """Trigger a factory reset over the device CLI: sysctl debug 1 / factory reset / y.

    The device reboots and rolls out the image previously written to /bkp by write-recovery.
    """
    host, port = live_device

    def _drain(bsb, secs):
        # Read whatever the device sends within `secs` (eol that never matches => time-bounded).
        return bsb.read.until_timeout("\x00", timeout=secs)

    def _reset():
        with BSB_Lite((host, port)) as bsb:
            bsb.send("sysctl debug 1\r")
            _drain(bsb, 1)
            bsb.send("factory_reset\r")
            _drain(bsb, 1)          # let the confirmation prompt render before answering
            bsb.send("y\r")
            _drain(bsb, 3)
            time.sleep(1)           # let the device act on the confirmation before the socket closes

    return _reset
