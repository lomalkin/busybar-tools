"""CLI parsing/validation tests with command dispatch mocked out."""
import sys

import pytest

import busybar_tools.cli as cli
from busybar_tools.cli import busybar_main


def run_cli(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["busybar"] + argv)
    return busybar_main()


@pytest.mark.parametrize("cmd", ["install", "fetch", "write-recovery"])
def test_source_is_required(monkeypatch, cmd):
    assert run_cli(monkeypatch, [cmd]) == 2


def test_auto_install_rejects_firmware_flags(monkeypatch):
    # autodetect-only: no -t override allowed
    assert run_cli(monkeypatch, ["auto-install", "-t", "22", "dev"]) == 2


def test_auto_install_defaults_to_release(monkeypatch):
    captured = {}

    def fake_auto_install(args):
        captured["source"] = args.source
        return 0

    monkeypatch.setattr(cli, "run_auto_install", fake_auto_install)
    ret = run_cli(monkeypatch, ["auto-install"])
    assert ret == 0
    assert captured["source"] == "release"


@pytest.mark.parametrize("argv,expected", [
    (["auto-install"], True),
    (["auto-install", "--via-storage"], True),
    (["auto-install", "--via-http"], False),
])
def test_auto_install_transport_options(monkeypatch, argv, expected):
    captured = {}

    def fake_auto_install(args):
        captured["via_storage"] = args.via_storage
        return 0

    monkeypatch.setattr(cli, "run_auto_install", fake_auto_install)
    ret = run_cli(monkeypatch, argv)
    assert ret == 0
    assert captured["via_storage"] is expected


def test_install_accepts_arbitrary_target(monkeypatch):
    # The closed {20,21,22} list was removed; any integer target must now parse.
    captured = {}

    def fake_install(args):
        captured["target"] = args.target
        return 0

    monkeypatch.setattr(cli, "run_install", fake_install)
    ret = run_cli(monkeypatch, ["install", "-t", "23", "dev"])
    assert ret == 0
    assert captured["target"] == 23


def _capture_bundle(monkeypatch, argv):
    """Parse `argv`, returning the resolved update_bundle_type (run_* mocked out)."""
    captured = {}

    def f(args):
        captured["bundle"] = args.update_bundle_type
        return 0

    monkeypatch.setattr(cli, "run_install", f)
    monkeypatch.setattr(cli, "run_fetch", f)
    monkeypatch.setattr(cli, "run_write_recovery", f)
    run_cli(monkeypatch, argv)
    return captured["bundle"]


@pytest.mark.parametrize("cmd,expected", [
    ("install", "update"),
    ("fetch", "update"),
    ("write-recovery", "bkp"),
])
def test_default_bundle_type_per_command(monkeypatch, cmd, expected):
    # Regression: write-recovery's --bkp default must not leak into install/fetch.
    assert _capture_bundle(monkeypatch, [cmd, "dev"]) == expected


def test_bundle_type_overrides(monkeypatch):
    assert _capture_bundle(monkeypatch, ["install", "--bkp", "dev"]) == "bkp"
    assert _capture_bundle(monkeypatch, ["write-recovery", "--update", "dev"]) == "update"


def test_install_signed_and_unsigned_are_mutually_exclusive(monkeypatch):
    assert run_cli(monkeypatch, ["install", "--signed", "--unsigned", "dev"]) == 2


def test_install_via_http_with_no_install_errors(monkeypatch):
    assert run_cli(monkeypatch, ["install", "--via-http", "--no-install", "dev"]) == 2


def test_recover_defaults(monkeypatch):
    captured = {}

    def fake_recover(args):
        captured["source"] = args.source
        captured["target"] = args.target
        captured["backend"] = args.backend
        captured["manual_dfu"] = args.manual_dfu
        captured["no_install_dfu_tool"] = args.no_install_dfu_tool
        captured["wait_timeout"] = args.wait_timeout
        return 0

    monkeypatch.setattr(cli, "run_recover", fake_recover)
    ret = run_cli(monkeypatch, ["recover"])
    assert ret == 0
    assert captured == {
        "source": "release",
        "target": "auto",
        "backend": "pyusb",
        "manual_dfu": False,
        "no_install_dfu_tool": False,
        "wait_timeout": 120,
    }


def test_help_exits_zero_and_mentions_auto_install(monkeypatch, capsys):
    assert run_cli(monkeypatch, ["--help"]) == 0
    assert "auto-install" in capsys.readouterr().out


def test_version_exits_zero_without_command(monkeypatch, capsys):
    assert run_cli(monkeypatch, ["--version"]) == 0
    assert "busybar-tools" in capsys.readouterr().out


def test_command_registration_order(monkeypatch, capsys):
    assert run_cli(monkeypatch, ["--help"]) == 0
    out = capsys.readouterr().out
    for command in [
        "auto-install",
        "cli",
        "recover",
        "storage",
        "install",
        "fetch",
        "write-recovery",
        "install-onboard",
        "wait",
        "clean",
    ]:
        assert command in out
