"""Unit tests for run_recover orchestration (USB and device interaction mocked)."""
import types

import pytest

import busybar_tools as bt
import busybar_tools.dfu

from test_dfu import _write_dfu


class FakeBackend:
    supports_reset_fallback = False

    def __init__(self, connected=1):
        self.connected = connected
        self.flashed = []
        self.left_dfu = 0
        self.leave_status_uncertain = False

    def find_devices(self):
        return self.connected

    def program_firmware(self, fw_file, reset=False):
        self.flashed.append((fw_file, reset))

    def leave_dfu(self):
        self.left_dfu += 1


def _args(**kw):
    base = dict(
        device="10.0.0.1", port=23, verbose=False,
        source="release", target="22", file=None,
        backend="pyusb", dfu_tool=None, install_dfu_tool=False,
        manual_dfu=False, dfu_timeout=1, wait_timeout=1,
        no_wait_after=False, confirm_timeout=0,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


@pytest.fixture
def quiet(monkeypatch):
    """Silence the countdown and network waits."""
    monkeypatch.setattr(bt, "confirm_countdown", lambda action, seconds: None)
    monkeypatch.setattr(bt, "wait_for_device", lambda *a, **k: {"success": True})


@pytest.fixture
def backend(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(bt.dfu, "ensure_recovery_backend", lambda *a, **k: fake)
    return fake


def test_recover_happy_path_flashes_and_leaves_dfu(tmp_path, quiet, backend):
    path = _write_dfu(tmp_path, target_name="BUSY-f22")

    assert bt.run_recover(_args(file=path)) == 0
    assert backend.flashed == [(path, False)]
    assert backend.left_dfu == 1


def test_recover_rejects_wrong_target_before_flashing(tmp_path, quiet, backend):
    path = _write_dfu(tmp_path, target_name="BUSY-f21")

    assert bt.run_recover(_args(file=path, target="22")) == 1
    assert backend.flashed == []


def test_recover_rejects_corrupt_image_before_flashing(tmp_path, quiet, backend):
    path = _write_dfu(tmp_path, corrupt_crc=True)

    assert bt.run_recover(_args(file=path)) == 1
    assert backend.flashed == []


def test_recover_auto_target_requires_reachable_device(tmp_path, quiet, backend, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no route to host")

    monkeypatch.setattr(bt, "device_read_info", boom)
    path = _write_dfu(tmp_path)

    assert bt.run_recover(_args(file=path, target="auto")) == 1
    assert backend.flashed == []


def test_recover_fails_when_backend_unavailable(monkeypatch, quiet):
    def unavailable(*a, **k):
        raise RuntimeError("PyUSB backend is not available")

    monkeypatch.setattr(bt.dfu, "ensure_recovery_backend", unavailable)
    assert bt.run_recover(_args()) == 1
