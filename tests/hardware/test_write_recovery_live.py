"""Live-device flash test: write a pinned, known-good bundle into the recovery partition.

ALWAYS writes WRITE_RECOVERY_VERSION (see conftest) so the stand keeps a known recovery image.
write-recovery does not reboot — it overwrites /bkp. Run with: pytest --run-flash.
"""
import pytest

import busybar_tools as bt


@pytest.mark.flash
def test_write_recovery_pinned(make_args, autodetect, recovery_version, live_device):
    host, port = live_device
    args = make_args(
        source=recovery_version, target=autodetect["target"], signed=autodetect["signed"],
        update_bundle_type="bkp", confirm_timeout=0,
    )
    assert bt.run_write_recovery(args) == 0
    # No reboot: the device should still answer right after the write.
    info = bt.device_read_info(
        host, port, retries=5, delay=2,
        required_keys=bt._VERSION_FIELDS + bt._DETECT_FIELDS,
    )
    assert info.get("u5_firmware_target")
