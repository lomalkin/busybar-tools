"""Flash finalizer (runs LAST): factory reset rolls out the image written to /bkp.

write-recovery (earlier flash test) writes WRITE_RECOVERY_VERSION into the recovery partition;
this test triggers a factory reset, which boots that image - leaving the stand in a known state.
Run with: pytest --run-flash  (slow: reboot, minutes).
"""
import pytest

import busybar_tools as bt
from busybar_tools.device import _DETECT_FIELDS, _VERSION_FIELDS

_READY = _VERSION_FIELDS + _DETECT_FIELDS


@pytest.mark.flash_final
def test_factory_reset_rolls_out_recovery(factory_reset, wait_until_back, recovery_version):
    factory_reset()
    info = wait_until_back()
    assert info.get("u5_firmware_target")
    # Recovery image written earlier (recovery_version) should now be the running firmware.
    # A tagged build reports the tag in branch and/or version.
    running = (info.get("u5_firmware_branch"), info.get("u5_firmware_version"))
    assert recovery_version in running, (
        f"factory reset did not roll out {recovery_version}; device reports {running}"
    )
