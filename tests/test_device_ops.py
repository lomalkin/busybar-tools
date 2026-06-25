"""Unit tests for device-facing helpers, with the device layer mocked out."""
import types

import pytest

import busybar_tools as bt


def test_wait_for_device_maybe_skips_with_no_wait(monkeypatch):
    calls = []
    monkeypatch.setattr(bt, "wait_for_device", lambda *a, **k: calls.append(1))
    bt.wait_for_device_maybe(types.SimpleNamespace(no_wait=True, device="x", verbose=True))
    assert calls == []
    bt.wait_for_device_maybe(types.SimpleNamespace(no_wait=False, device="x", verbose=True))
    assert calls == [1]


def test_install_onboard_routing(monkeypatch):
    captured = {}

    def fake_upload(args, update_dir):
        captured["dir"] = update_dir
        return 0

    monkeypatch.setattr(bt, "run_update_from_storage", fake_upload)

    bt.run_update_local(types.SimpleNamespace(device_path="recovery"))
    assert captured["dir"] == bt.DIR_BSB_RECOVERY

    bt.run_update_local(types.SimpleNamespace(device_path=""))
    assert captured["dir"] == bt.DIR_BSB_TMP_UPDATE

    bt.run_update_local(types.SimpleNamespace(device_path="/ext/tmp/update"))
    assert captured["dir"] == "/ext/tmp/update"


def test_run_storage_maps_device_and_strips_dashdash(monkeypatch):
    monkeypatch.setattr(bt, "wait_for_device_maybe", lambda args: None)
    captured = {}
    monkeypatch.setattr(bt.subprocess, "call", lambda cmd, *a, **k: captured.setdefault("cmd", cmd) or 0)

    bt.run_storage(types.SimpleNamespace(
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

    monkeypatch.setattr(bt, "BSB_Lite", FakeBSB)
    assert bt.device_read_info("10.0.0.1", 23) == {"u5_firmware_target": "22"}


def test_device_read_info_raises_after_retries(monkeypatch):
    monkeypatch.setattr(bt.time, "sleep", lambda *_: None)

    class Boom:
        def __init__(self, *a, **k):
            raise OSError("no device")

    monkeypatch.setattr(bt, "BSB_Lite", Boom)
    with pytest.raises(RuntimeError):
        bt.device_read_info("10.0.0.9", 23, retries=3, delay=0)


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
    monkeypatch.setattr(bt.time, "sleep", lambda *_: None)
    partial = {"u5_firmware_branch": "dev", "u5_firmware_commit": "aaaa", "u5_firmware_builddate": "2026-06-17"}
    complete = dict(partial, sl_firmware_branch="dev", sl_firmware_commit="aaaa", sl_firmware_builddate="2026-06-17")
    monkeypatch.setattr(bt, "BSB_Lite", _fake_bsb_returning([dict(partial), dict(partial), dict(complete)]))

    info = bt.device_read_info("10.0.0.1", 23, retries=10, delay=0, required_keys=bt._VERSION_FIELDS)
    assert info.get("sl_firmware_commit") == "aaaa"
    assert bt._device_info_ready(info, bt._VERSION_FIELDS)


def test_device_read_info_returns_partial_after_budget(monkeypatch):
    monkeypatch.setattr(bt.time, "sleep", lambda *_: None)
    partial = {"u5_firmware_branch": "dev", "u5_firmware_commit": "aaaa", "u5_firmware_builddate": "2026-06-17"}
    # Always incomplete (no sl_* fields).
    monkeypatch.setattr(bt, "BSB_Lite", _fake_bsb_returning([dict(partial)] * 5))

    info = bt.device_read_info("10.0.0.1", 23, retries=3, delay=0, required_keys=bt._VERSION_FIELDS)
    assert info.get("u5_firmware_commit") == "aaaa"
    assert not bt._device_info_ready(info, bt._VERSION_FIELDS)  # partial, but returned (no raise)
