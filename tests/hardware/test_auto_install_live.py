"""Live-device flash tests: full auto-install cycle (autodetect -> install -> reboot -> report).

Run with: pytest --run-flash  (slow: real flash + reboot, minutes).
"""
import pytest

import busybar_tools as bt

_READY = bt._VERSION_FIELDS + bt._DETECT_FIELDS


@pytest.mark.flash
@pytest.mark.parametrize("via_storage", [True, False], ids=["storage", "http"])
def test_auto_install_flash(make_args, flash_source, live_device, via_storage):
    host, port = live_device
    args = make_args(source=flash_source, via_storage=via_storage, no_wait_after=False)
    assert bt.run_auto_install(args) == 0  # waits for the reboot internally
    info = bt.device_read_info(host, port, retries=5, delay=2, required_keys=_READY)
    assert info.get("u5_firmware_target")


@pytest.mark.flash
def test_auto_install_no_wait_after(make_args, flash_source, wait_until_back):
    args = make_args(source=flash_source, via_storage=True, no_wait_after=True)
    assert bt.run_auto_install(args) == 0  # returns right after invoking install
    info = wait_until_back()               # we wait for the reboot ourselves
    assert info.get("u5_firmware_target")
