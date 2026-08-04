"""Unit tests for run_auto_install guards that don't require a device."""
import pytest

import busybar_tools as bt
from busybar_tools.errors import FirmwareError


def _args(source):
    return bt.AutoInstallOptions(bt.DeviceEndpoint("10.0.0.1", 23), source, verbose=False)


def test_auto_install_rejects_local_file(tmp_path):
    f = tmp_path / "x.tgz"
    f.write_text("x")
    with pytest.raises(FirmwareError):
        bt.run_auto_install(_args(str(f)))


def test_auto_install_rejects_local_dir(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    with pytest.raises(FirmwareError):
        bt.run_auto_install(_args(str(d)))
