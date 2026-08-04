"""Unit tests for device-facing application services."""

from types import SimpleNamespace

import pytest

import busybar_tools.commands.factory_reset as factory_reset_cmd
import busybar_tools.commands.install as install_cmd
import busybar_tools.commands.recover as recover_cmd
import busybar_tools.commands.storage as storage_cmd
import busybar_tools.device.info as device_info
import busybar_tools.device.operations as device_ops
from busybar_tools.config import DIR_BSB_RECOVERY, DIR_BSB_TMP_UPDATE
from busybar_tools.dfu import DfuDevice
from busybar_tools.errors import RecoveryError
from busybar_tools.options import (
    DeviceEndpoint,
    FactoryResetOptions,
    InstallOnboardOptions,
    RecoveryOptions,
)

ENDPOINT = DeviceEndpoint("10.0.4.20", 23)


def test_ensure_device_reachable_can_be_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(device_ops, "wait_for_device", lambda *args, **kwargs: calls.append(args))
    device_ops.ensure_device_reachable(ENDPOINT, enabled=False)
    assert calls == []
    device_ops.ensure_device_reachable(ENDPOINT, enabled=True)
    assert calls == [(ENDPOINT.host,)]


def test_install_onboard_routing(monkeypatch):
    captured = []
    monkeypatch.setattr(
        install_cmd,
        "_update_from_storage",
        lambda endpoint, path, *args, **kwargs: captured.append(path) or 0,
    )
    for requested in ("recovery", "", "/ext/tmp/update"):
        install_cmd.run_update_local(InstallOnboardOptions(ENDPOINT, requested))
    assert captured == [DIR_BSB_RECOVERY, DIR_BSB_TMP_UPDATE, "/ext/tmp/update"]


def test_factory_reset_shipping_mode_flow(monkeypatch):
    calls = []

    class FakeRead:
        def until_timeout(self, delimiter, timeout=None):
            calls.append(("read", delimiter, timeout))
            return b"Warning! This will wipe all the data from the device! Are you sure? y/n\r\n"

    class FakeCli:
        def __init__(self, address):
            calls.append(("init", address))
            self.read = FakeRead()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def send(self, line):
            calls.append(("send", line))

    monkeypatch.setattr(factory_reset_cmd, "BusybarCli", FakeCli)
    monkeypatch.setattr(factory_reset_cmd, "ensure_device_reachable", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        factory_reset_cmd,
        "wait_for_device",
        lambda *args, **kwargs: calls.append(("wait", args, kwargs)),
    )
    monkeypatch.setattr(factory_reset_cmd.time, "sleep", lambda seconds: None)

    result = factory_reset_cmd.run_factory_reset(FactoryResetOptions(
        ENDPOINT, shipping_mode=True, offline_timeout=7, verbose=False,
    ))
    assert result == 0
    assert ("send", "sysctl debug 1\r") in calls
    assert ("send", "factory_reset -s\r") in calls
    assert ("send", "y\r") in calls
    assert any(call[0] == "wait" and call[2].get("success_ping_as") is False for call in calls)


def test_storage_service_uses_device_endpoint(monkeypatch):
    captured = {}

    class FakeStorage:
        def __init__(self, address):
            captured["address"] = address

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_tree(self, path):
            captured["path"] = path
            return iter(["/ext/file.txt, size 4"])

    monkeypatch.setattr(storage_cmd, "ensure_device_reachable", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_cmd, "DeviceStorage", FakeStorage)
    result = storage_cmd.StorageService(ENDPOINT, wait_before=False).list("/ext")
    assert captured == {"address": ENDPOINT.address, "path": "/ext"}
    assert result == ["/ext/file.txt, size 4"]


class FakeInfoCli:
    responses = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def device_info(self):
        return self.responses.pop(0)


def test_read_device_info_success(monkeypatch):
    FakeInfoCli.responses = [{"u5_firmware_target": "22"}]
    monkeypatch.setattr(device_info, "BusybarCli", FakeInfoCli)
    assert device_info.read_device_info(ENDPOINT) == {"u5_firmware_target": "22"}


def test_read_device_info_raises_after_retries(monkeypatch):
    class Boom:
        def __init__(self, *args, **kwargs):
            raise OSError("no device")

    monkeypatch.setattr(device_info, "BusybarCli", Boom)
    monkeypatch.setattr(device_info.time, "sleep", lambda *_: None)
    with pytest.raises(RuntimeError):
        device_info.read_device_info(ENDPOINT, retries=3, delay=0)


def test_read_device_info_polls_until_complete(monkeypatch):
    partial = {"u5_firmware_branch": "dev", "u5_firmware_commit": "aaaa"}
    complete = dict(partial, u5_firmware_builddate="date")
    FakeInfoCli.responses = [dict(partial), dict(complete)]
    monkeypatch.setattr(device_info, "BusybarCli", FakeInfoCli)
    monkeypatch.setattr(device_info.time, "sleep", lambda *_: None)
    result = device_info.read_device_info(
        ENDPOINT, retries=3, delay=0,
        required_keys=("u5_firmware_branch", "u5_firmware_commit", "u5_firmware_builddate"),
    )
    assert result == complete


def _recovery_options(**changes):
    values = dict(
        endpoint=ENDPOINT, source="release", file=None, target="auto", manual_dfu=False,
        dfu_tool=None, install_dfu_tool=False, backend="pyusb", wait_after=True,
        wait_timeout=1, assume_yes=True, verbose=False,
    )
    values.update(changes)
    return RecoveryOptions(**values)


def test_recover_refuses_multiple_generic_stm32_dfu_devices():
    devices = [
        DfuDevice("usb:1", 0x0483, 0xDF11, path="1-1"),
        DfuDevice("usb:2", 0x0483, 0xDF11, path="1-2"),
    ]
    with pytest.raises(RecoveryError, match="Multiple STM32 DFU devices"):
        recover_cmd._single_dfu_device(devices)


def test_recover_does_not_read_ip_when_device_is_already_in_dfu(monkeypatch):
    device = DfuDevice("usb:1", 0x0483, 0xDF11, path="1-2")
    monkeypatch.setattr(
        recover_cmd,
        "read_device_info",
        lambda *args, **kwargs: pytest.fail("device_info must not be called for an existing DFU device"),
    )

    with pytest.raises(RecoveryError, match="already in DFU mode"):
        recover_cmd._recover_resolve_target(_recovery_options(), device)


def test_recover_infers_target_from_local_dfu_when_already_in_dfu(monkeypatch, tmp_path):
    device = DfuDevice("usb:1", 0x0483, 0xDF11, path="1-2")
    firmware = tmp_path / "recovery.dfu"
    firmware.write_bytes(b"dfu")
    monkeypatch.setattr(
        "busybar_tools.dfu.parse_dfuse_file",
        lambda path: SimpleNamespace(target_name="Flipper F21"),
    )

    assert recover_cmd._recover_resolve_target(
        _recovery_options(file=str(firmware)), device,
    ) == 21


def test_recover_timeout_after_flash_returns_success(monkeypatch, tmp_path, capsys):
    class FakeBackend:
        def list_devices(self):
            return [DfuDevice("usb:1", 0x0483, 0xDF11, path="1-2")]

        def select_device(self, device):
            self.device = device

        def program_firmware(self, *args, **kwargs):
            pass

        def leave_dfu(self, **kwargs):
            pass

    firmware = tmp_path / "recovery.dfu"
    firmware.write_bytes(b"dfu")
    monkeypatch.setattr(recover_cmd, "_recover_resolve_target", lambda *args: 22)
    monkeypatch.setattr("busybar_tools.dfu.ensure_recovery_backend", lambda *args, **kwargs: FakeBackend())
    monkeypatch.setattr("busybar_tools.dfu.resolve_recovery_dfu", lambda *args, **kwargs: str(firmware))
    monkeypatch.setattr(
        "busybar_tools.dfu.validate_recovery_image",
        lambda *args, **kwargs: SimpleNamespace(address=0x08000000, data=b"fw", target_name="Flipper F22"),
    )
    monkeypatch.setattr(recover_cmd, "wait_for_device", lambda *args, **kwargs: {"success": False})
    assert recover_cmd.run_recover(_recovery_options()) == 0
    assert "Hold Start and Back" in capsys.readouterr().out


def test_recover_prints_reset_hint_when_leave_status_is_uncertain(monkeypatch, tmp_path, capsys):
    class FakeBackend:
        leave_status_uncertain = True

        def list_devices(self):
            return [DfuDevice("usb:1", 0x0483, 0xDF11, path="1-2")]

        def select_device(self, device):
            self.device = device

        def program_firmware(self, *args, **kwargs):
            pass

        def leave_dfu(self, **kwargs):
            pass

    firmware = tmp_path / "recovery.dfu"
    firmware.write_bytes(b"dfu")
    monkeypatch.setattr(recover_cmd, "_recover_resolve_target", lambda *args: 22)
    monkeypatch.setattr("busybar_tools.dfu.ensure_recovery_backend", lambda *args, **kwargs: FakeBackend())
    monkeypatch.setattr("busybar_tools.dfu.resolve_recovery_dfu", lambda *args, **kwargs: str(firmware))
    monkeypatch.setattr(
        "busybar_tools.dfu.validate_recovery_image",
        lambda *args, **kwargs: SimpleNamespace(address=0x08000000, data=b"fw", target_name="Flipper F22"),
    )
    monkeypatch.setattr(recover_cmd, "wait_for_device", lambda *args, **kwargs: {"success": True})
    assert recover_cmd.run_recover(_recovery_options()) == 0
    output = capsys.readouterr().out
    assert "Hold Start and Back" in output
    assert "Recovery DFU flashing complete." in output
