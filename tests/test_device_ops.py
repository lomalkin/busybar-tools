"""Unit tests for device-facing helpers, with the device layer mocked out."""
import types

import pytest

import busybar_tools.device as device_mod
import busybar_tools.commands.install as install_cmd
import busybar_tools.commands.recover as recover_cmd
import busybar_tools.commands.storage as storage_cmd
from busybar_tools.config import DIR_BSB_RECOVERY, DIR_BSB_TMP_UPDATE


def test_wait_for_device_maybe_skips_with_no_wait(monkeypatch):
    calls = []
    monkeypatch.setattr(device_mod, "wait_for_device", lambda *a, **k: calls.append(1))
    device_mod.wait_for_device_maybe(types.SimpleNamespace(no_wait=True, device="x", verbose=True))
    assert calls == []
    device_mod.wait_for_device_maybe(types.SimpleNamespace(no_wait=False, device="x", verbose=True))
    assert calls == [1]


def test_install_onboard_routing(monkeypatch):
    captured = {}

    def fake_upload(args, update_dir):
        captured["dir"] = update_dir
        return 0

    monkeypatch.setattr(install_cmd, "run_update_from_storage", fake_upload)

    install_cmd.run_update_local(types.SimpleNamespace(device_path="recovery"))
    assert captured["dir"] == DIR_BSB_RECOVERY

    install_cmd.run_update_local(types.SimpleNamespace(device_path=""))
    assert captured["dir"] == DIR_BSB_TMP_UPDATE

    install_cmd.run_update_local(types.SimpleNamespace(device_path="/ext/tmp/update"))
    assert captured["dir"] == "/ext/tmp/update"


def test_run_storage_maps_device_and_strips_dashdash(monkeypatch):
    monkeypatch.setattr(storage_cmd, "wait_for_device_maybe", lambda args: None)
    captured = {}
    monkeypatch.setattr(storage_cmd.subprocess, "call", lambda cmd, *a, **k: captured.setdefault("cmd", cmd) or 0)

    storage_cmd.run_storage(types.SimpleNamespace(
        device="10.0.4.20", port=23, verbose=True,
        storage_args=["--", "list", "/ext"], no_wait=False,
    ))

    cmd = captured["cmd"]
    assert "--host" in cmd and "10.0.4.20" in cmd
    assert "-p" in cmd and "23" in cmd
    assert "--" not in cmd
    assert cmd[-2:] == ["list", "/ext"]
    # device options precede the storage sub-command
    assert cmd.index("--host") < cmd.index("list")


def test_device_read_info_success(monkeypatch):
    class FakeBSB:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def device_info(self):
            return {"u5_firmware_target": "22"}

    monkeypatch.setattr(device_mod, "BSB_Lite", FakeBSB)
    assert device_mod.device_read_info("10.0.0.1", 23) == {"u5_firmware_target": "22"}


def test_device_read_info_raises_after_retries(monkeypatch):
    monkeypatch.setattr(device_mod.time, "sleep", lambda *_: None)

    class Boom:
        def __init__(self, *a, **k):
            raise OSError("no device")

    monkeypatch.setattr(device_mod, "BSB_Lite", Boom)
    with pytest.raises(RuntimeError):
        device_mod.device_read_info("10.0.0.9", 23, retries=3, delay=0)


def _fake_bsb_returning(responses):
    """Build a BSB_Lite stub that yields successive device_info() dicts from `responses`."""
    seq = iter(responses)

    class FakeBSB:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def device_info(self):
            return next(seq)

    return FakeBSB


def test_device_read_info_polls_until_complete(monkeypatch):
    monkeypatch.setattr(device_mod.time, "sleep", lambda *_: None)
    partial = {"u5_firmware_branch": "dev", "u5_firmware_commit": "aaaa", "u5_firmware_builddate": "2026-06-17"}
    complete = dict(partial, sl_firmware_branch="dev", sl_firmware_commit="aaaa", sl_firmware_builddate="2026-06-17")
    monkeypatch.setattr(device_mod, "BSB_Lite", _fake_bsb_returning([dict(partial), dict(partial), dict(complete)]))

    info = device_mod.device_read_info("10.0.0.1", 23, retries=10, delay=0, required_keys=device_mod._VERSION_FIELDS)
    assert info.get("sl_firmware_commit") == "aaaa"
    assert device_mod._device_info_ready(info, device_mod._VERSION_FIELDS)


def test_device_read_info_returns_partial_after_budget(monkeypatch):
    monkeypatch.setattr(device_mod.time, "sleep", lambda *_: None)
    partial = {"u5_firmware_branch": "dev", "u5_firmware_commit": "aaaa", "u5_firmware_builddate": "2026-06-17"}
    # Always incomplete (no sl_* fields).
    monkeypatch.setattr(device_mod, "BSB_Lite", _fake_bsb_returning([dict(partial)] * 5))

    info = device_mod.device_read_info("10.0.0.1", 23, retries=3, delay=0, required_keys=device_mod._VERSION_FIELDS)
    assert info.get("u5_firmware_commit") == "aaaa"
    assert not device_mod._device_info_ready(info, device_mod._VERSION_FIELDS)  # partial, but returned (no raise)


def test_recover_timeout_after_flash_returns_success(monkeypatch, tmp_path, capsys):
    class FakeBackend:
        def find_devices(self):
            return True

        def program_firmware(self, *a, **k):
            return None

        def leave_dfu(self):
            return None

    fw = tmp_path / "recovery.dfu"
    fw.write_bytes(b"dfu")

    monkeypatch.setattr(recover_cmd, "_recover_resolve_target", lambda args: 22)
    monkeypatch.setattr("busybar_tools.dfu.ensure_recovery_backend", lambda *a, **k: FakeBackend())
    monkeypatch.setattr("busybar_tools.dfu.resolve_recovery_dfu", lambda *a, **k: str(fw))
    monkeypatch.setattr(recover_cmd, "wait_for_device", lambda *a, **k: {"success": False})

    ret = recover_cmd.run_recover(types.SimpleNamespace(
        device="10.0.4.20",
        port=23,
        source="release",
        file=None,
        target="auto",
        manual_dfu=False,
        dfu_tool=None,
        no_install_dfu_tool=True,
        backend="pyusb",
        no_wait_after=False,
        wait_timeout=1,
        verbose=False,
    ))

    assert ret == 0
    assert "Hold Start and Back" in capsys.readouterr().out


def test_recover_prints_reset_hint_when_leave_status_is_uncertain(monkeypatch, tmp_path, capsys):
    class FakeBackend:
        leave_status_uncertain = True

        def find_devices(self):
            return True

        def program_firmware(self, *a, **k):
            return None

        def leave_dfu(self):
            return None

    fw = tmp_path / "recovery.dfu"
    fw.write_bytes(b"dfu")

    monkeypatch.setattr(recover_cmd, "_recover_resolve_target", lambda args: 22)
    monkeypatch.setattr("busybar_tools.dfu.ensure_recovery_backend", lambda *a, **k: FakeBackend())
    monkeypatch.setattr("busybar_tools.dfu.resolve_recovery_dfu", lambda *a, **k: str(fw))
    monkeypatch.setattr(recover_cmd, "wait_for_device", lambda *a, **k: {"success": True})

    ret = recover_cmd.run_recover(types.SimpleNamespace(
        device="10.0.4.20",
        port=23,
        source="release",
        file=None,
        target="auto",
        manual_dfu=False,
        dfu_tool=None,
        no_install_dfu_tool=True,
        backend="pyusb",
        no_wait_after=False,
        wait_timeout=1,
        verbose=False,
    ))

    out = capsys.readouterr().out
    assert ret == 0
    assert "Hold Start and Back" in out
    assert "Recovery DFU flashing complete." in out
