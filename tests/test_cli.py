"""CLI parsing and typed command dispatch tests."""

import sys

import pytest

from busybar_tools.cli import busybar_main
from busybar_tools.config import DEVICE_IP_REF
import busybar_tools.presentation.device as device_cli
import busybar_tools.presentation.firmware as firmware_cli
import busybar_tools.presentation.storage as storage_cli


def run_cli(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["busybar"] + argv)
    return busybar_main()


@pytest.mark.parametrize("command", ["install", "fetch", "write-recovery"])
def test_source_is_required(monkeypatch, capsys, command):
    assert run_cli(monkeypatch, [command]) == 2
    error = capsys.readouterr().err
    assert "Missing argument" in error
    assert f"busybar {command}" in error
    assert "Traceback" not in error


def test_unknown_command_prints_root_help(monkeypatch, capsys):
    assert run_cli(monkeypatch, ["does-not-exist"]) == 2
    error = capsys.readouterr().err
    assert "No such command 'does-not-exist'" in error
    assert "Usage: busybar [OPTIONS] COMMAND [ARGS]..." in error
    assert "auto-install" in error
    assert "Traceback" not in error


def test_auto_install_rejects_firmware_flags(monkeypatch):
    assert run_cli(monkeypatch, ["auto-install", "-t", "22", "dev"]) == 2


def test_auto_install_defaults_to_release(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        firmware_cli,
        "run_auto_install",
        lambda options: captured.setdefault("options", options) and 0,
    )
    assert run_cli(monkeypatch, ["auto-install"]) == 0
    assert captured["options"].source == "release"


@pytest.mark.parametrize("argv,expected", [
    (["auto-install"], True),
    (["auto-install", "--via-storage"], True),
    (["auto-install", "--via-http"], False),
])
def test_auto_install_transport_options(monkeypatch, argv, expected):
    captured = {}

    def fake(options):
        captured["options"] = options
        return 0

    monkeypatch.setattr(firmware_cli, "run_auto_install", fake)
    assert run_cli(monkeypatch, argv) == 0
    assert captured["options"].via_storage is expected


def test_install_accepts_arbitrary_target(monkeypatch):
    captured = {}

    def fake(options):
        captured["options"] = options
        return 0

    monkeypatch.setattr(firmware_cli, "run_install", fake)
    assert run_cli(monkeypatch, ["install", "-t", "23", "dev"]) == 0
    assert captured["options"].firmware.target == 23


def _capture_bundle(monkeypatch, argv):
    captured = {}

    def fake(options):
        captured["bundle"] = options.firmware.bundle_type
        return 0

    monkeypatch.setattr(firmware_cli, "run_install", fake)
    monkeypatch.setattr(firmware_cli, "run_fetch", fake)
    monkeypatch.setattr(firmware_cli, "run_write_recovery", fake)
    run_cli(monkeypatch, argv)
    return captured["bundle"]


@pytest.mark.parametrize("command,expected", [
    ("install", "update"),
    ("fetch", "update"),
    ("write-recovery", "bkp"),
])
def test_default_bundle_type_per_command(monkeypatch, command, expected):
    assert _capture_bundle(monkeypatch, [command, "dev"]) == expected


def test_bundle_type_overrides(monkeypatch):
    assert _capture_bundle(monkeypatch, ["install", "--bkp", "dev"]) == "bkp"
    assert _capture_bundle(monkeypatch, ["write-recovery", "--update", "dev"]) == "update"


def test_mutually_exclusive_options(monkeypatch):
    assert run_cli(monkeypatch, ["install", "--signed", "--unsigned", "dev"]) == 2
    assert run_cli(monkeypatch, ["install", "--via-http", "--no-install", "dev"]) == 2


def test_recover_defaults(monkeypatch):
    captured = {}

    def fake(options):
        captured["options"] = options
        return 0

    monkeypatch.setattr(firmware_cli, "run_recover", fake)
    assert run_cli(monkeypatch, ["recover"]) == 0
    options = captured["options"]
    assert options.source == "release"
    assert options.target == "auto"
    assert options.backend == "pyusb"
    assert options.manual_dfu is False
    assert options.install_dfu_tool is True
    assert options.wait_timeout == 120


def test_report_options(monkeypatch):
    captured = {}

    def fake(options, **kwargs):
        captured["options"] = options
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(device_cli, "run_report", fake)
    assert run_cli(monkeypatch, [
        "report", "-d", "r", "-p", "2323", "--http-port", "8080",
        "-o", "report.zip", "--api-token", "1234", "--timeout", "9",
        "--no-wait", "--no-logs", "--no-screens", "--no-cli",
    ]) == 0
    options = captured["options"]
    assert options.endpoint.host == DEVICE_IP_REF
    assert options.endpoint.port == 2323
    assert options.http_port == 8080
    assert options.output == "report.zip"
    assert options.api_token == "1234"
    assert options.timeout == 9
    assert captured["wait_before"] is False
    assert options.include_logs is False
    assert options.include_screens is False
    assert options.include_cli is False


def test_factory_reset_options(monkeypatch):
    captured = {}

    def fake(options):
        captured["options"] = options
        return 0

    monkeypatch.setattr(device_cli, "run_factory_reset", fake)
    assert run_cli(monkeypatch, [
        "factory-reset", "-d", "r", "-p", "2323", "--no-wait",
        "--shipping-mode", "--no-wait-after", "--offline-timeout", "9",
    ]) == 0
    options = captured["options"]
    assert options.endpoint.host == DEVICE_IP_REF
    assert options.endpoint.port == 2323
    assert options.wait_before is False
    assert options.shipping_mode is True
    assert options.wait_after is False
    assert options.offline_timeout == 9


def test_storage_is_a_native_subcommand_group(monkeypatch):
    captured = {}

    class FakeStorageService:
        def __init__(self, endpoint, wait_before=True):
            captured["endpoint"] = endpoint
            captured["wait_before"] = wait_before

        def list(self, path):
            captured["path"] = path
            return ["/ext/file.txt, size 4"]

    monkeypatch.setattr(storage_cli, "StorageService", FakeStorageService)
    assert run_cli(monkeypatch, [
        "storage", "-d", "r", "-p", "2323", "--no-wait", "list", "/ext",
    ]) == 0
    assert captured["endpoint"].host == DEVICE_IP_REF
    assert captured["endpoint"].port == 2323
    assert captured["wait_before"] is False
    assert captured["path"] == "/ext"


def test_help_and_version(monkeypatch, capsys):
    assert run_cli(monkeypatch, ["--help"]) == 0
    assert "auto-install" in capsys.readouterr().out
    assert run_cli(monkeypatch, ["--version"]) == 0
    assert "busybar-tools" in capsys.readouterr().out


def test_command_registration_order(monkeypatch, capsys):
    assert run_cli(monkeypatch, ["--help"]) == 0
    output = capsys.readouterr().out
    for command in [
        "auto-install", "cli", "recover", "report", "storage", "install",
        "fetch", "write-recovery", "install-onboard", "factory-reset", "wait", "clean",
    ]:
        assert command in output
