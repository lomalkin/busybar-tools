"""Live-device flash tests: full auto-install cycle (autodetect -> install -> reboot -> report).

Run with: pytest --run-flash  (slow: real flash + reboot, minutes).
"""
import pytest

import busybar_tools as bt
from busybar_tools.device import DETECT_FIELDS, VERSION_FIELDS

_READY = VERSION_FIELDS + DETECT_FIELDS


@pytest.mark.flash
@pytest.mark.parametrize("via_storage", [True, False], ids=["storage", "http"])
def test_auto_install_flash(device_endpoint, flash_source, via_storage):
    options = bt.AutoInstallOptions(device_endpoint, flash_source, wait_before=False, via_storage=via_storage)
    assert bt.run_auto_install(options) == 0
    info = bt.read_device_info(device_endpoint, retries=5, delay=2, required_keys=_READY)
    assert info.get("u5_firmware_target")


@pytest.mark.flash
def test_auto_install_no_wait_after(device_endpoint, flash_source, wait_until_back):
    options = bt.AutoInstallOptions(device_endpoint, flash_source, wait_before=False, wait_after=False)
    assert bt.run_auto_install(options) == 0
    info = wait_until_back()               # we wait for the reboot ourselves
    assert info.get("u5_firmware_target")
