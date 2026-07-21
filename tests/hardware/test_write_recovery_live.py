"""Live-device flash test: write a pinned, known-good bundle into the recovery partition.

ALWAYS writes WRITE_RECOVERY_VERSION (see conftest) so the stand keeps a known recovery image.
write-recovery does not reboot - it overwrites /bkp. Run with: pytest --run-flash.
"""
import pytest

import busybar_tools as bt
from busybar_tools.device import DETECT_FIELDS, VERSION_FIELDS


@pytest.mark.flash
def test_write_recovery_pinned(device_endpoint, autodetect, recovery_version):
    selection = bt.FirmwareSelection(recovery_version, autodetect["target"], "bkp", autodetect["signed"], True)
    options = bt.WriteRecoveryOptions(device_endpoint, selection, wait_before=False, confirm_timeout=0)
    assert bt.run_write_recovery(options) == 0
    # No reboot: the device should still answer right after the write.
    info = bt.read_device_info(
        device_endpoint, retries=5, delay=2,
        required_keys=VERSION_FIELDS + DETECT_FIELDS,
    )
    assert info.get("u5_firmware_target")
