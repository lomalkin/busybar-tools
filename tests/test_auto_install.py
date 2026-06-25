"""Unit tests for run_auto_install guards that don't require a device."""
import types

import busybar_tools as bt


def _args(source):
    return types.SimpleNamespace(source=source, device="10.0.0.1", port=23, verbose=False)


def test_auto_install_rejects_local_file(tmp_path):
    f = tmp_path / "x.tgz"
    f.write_text("x")
    assert bt.run_auto_install(_args(str(f))) == 1


def test_auto_install_rejects_local_dir(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    assert bt.run_auto_install(_args(str(d))) == 1
