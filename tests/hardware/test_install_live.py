"""Live-device install tests."""

import pytest

import busybar_tools as bt


def _install_options(device_endpoint, autodetect, source, **overrides):
    bundle_type = overrides.pop("bundle_type", "update")
    selection = bt.FirmwareSelection(
        source, autodetect["target"], bundle_type, autodetect["signed"],
    )
    values = dict(
        endpoint=device_endpoint,
        firmware=selection,
        wait_before=False,
        via_storage=True,
        invoke_update=False,
    )
    values.update(overrides)
    return bt.InstallOptions(**values)


def test_install_stage_only(device_endpoint, flash_source, autodetect):
    assert bt.run_install(_install_options(device_endpoint, autodetect, flash_source)) == 0


def test_install_stage_from_url(device_endpoint, autodetect, flash_source):
    from busybar_tools.config import UPDATE_SERVER_BASE
    url = f"{UPDATE_SERVER_BASE}{flash_source}/"
    assert bt.run_install(_install_options(device_endpoint, autodetect, url)) == 0


def test_install_stage_from_local_file(device_endpoint, autodetect, prefetched_bundle):
    assert bt.run_install(_install_options(device_endpoint, autodetect, prefetched_bundle["file"])) == 0


def test_install_stage_from_local_dir(device_endpoint, autodetect, prefetched_bundle):
    assert bt.run_install(_install_options(device_endpoint, autodetect, prefetched_bundle["dir"])) == 0


def test_install_stage_bkp_bundle(device_endpoint, autodetect, flash_source):
    assert bt.run_install(
        _install_options(device_endpoint, autodetect, flash_source, bundle_type="bkp")
    ) == 0


@pytest.mark.flash
@pytest.mark.parametrize("via_storage", [True, False], ids=["storage", "http"])
def test_install_flash(device_endpoint, flash_source, autodetect, wait_until_back, via_storage):
    options = _install_options(
        device_endpoint,
        autodetect,
        flash_source,
        via_storage=via_storage,
        invoke_update=True,
    )
    assert bt.run_install(options) == 0
    info = wait_until_back()
    assert info.get("u5_firmware_target")
    assert info.get("u5_firmware_commit")
