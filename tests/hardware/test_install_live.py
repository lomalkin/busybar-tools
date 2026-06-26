"""Live-device install tests.

- Safe (`--run-hardware`): stage-only — uploads + verifies the bundle on the device WITHOUT
  invoking installation (no reboot, no firmware change).
- Flashing (`--run-flash`): actually installs over both transports and waits for the device to
  come back. Slow (minutes) — we just wait.
"""
import pytest

import busybar_tools as bt


def _stage_args(make_args, autodetect, **over):
    base = dict(
        target=autodetect["target"], signed=autodetect["signed"],
        update_bundle_type="update", via_storage=True, invoke_update=False,
    )
    base.update(over)
    return make_args(**base)


def test_install_stage_only(make_args, flash_source, autodetect):
    # Returns 0 only after upload + on-device verification succeed; no install is invoked.
    assert bt.run_install(_stage_args(make_args, autodetect, source=flash_source)) == 0


def test_install_stage_from_url(make_args, autodetect, flash_source):
    # Branch/tag resolves to an update-server folder URL — exercise the explicit-URL source.
    from busybar_tools.config import UPDATE_SERVER_BASE
    url = f"{UPDATE_SERVER_BASE}{flash_source}/"
    assert bt.run_install(_stage_args(make_args, autodetect, source=url)) == 0


def test_install_stage_from_local_file(make_args, autodetect, prefetched_bundle):
    assert bt.run_install(_stage_args(make_args, autodetect, source=prefetched_bundle.file)) == 0


def test_install_stage_from_local_dir(make_args, autodetect, prefetched_bundle):
    assert bt.run_install(_stage_args(make_args, autodetect, source=prefetched_bundle.dir)) == 0


def test_install_stage_bkp_bundle(make_args, autodetect, flash_source):
    assert bt.run_install(
        _stage_args(make_args, autodetect, source=flash_source, update_bundle_type="bkp")
    ) == 0


@pytest.mark.flash
@pytest.mark.parametrize("via_storage", [True, False], ids=["storage", "http"])
def test_install_flash(make_args, flash_source, autodetect, wait_until_back, via_storage):
    args = make_args(
        source=flash_source, target=autodetect["target"], signed=autodetect["signed"],
        update_bundle_type="update", via_storage=via_storage, invoke_update=True,
    )
    ret = bt.run_install(args)
    assert ret in (0, 200, None)  # storage -> 0; http -> HTTP status 200
    info = wait_until_back()      # device reboots & reapplies — just wait
    assert info.get("u5_firmware_target")
    assert info.get("u5_firmware_commit")
