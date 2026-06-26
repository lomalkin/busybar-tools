"""Argparse-level tests: only argument parsing/validation (no dispatch to device)."""
import sys

import pytest

import busybar_tools.cli as cli
from busybar_tools.cli import busybar_main


def run_cli(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["busybar"] + argv)
    return busybar_main()


@pytest.mark.parametrize("cmd", ["install", "fetch", "write-recovery"])
def test_source_is_required(monkeypatch, cmd):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, [cmd])
    assert exc.value.code == 2


def test_auto_install_rejects_firmware_flags(monkeypatch):
    # autodetect-only: no -t override allowed
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, ["auto-install", "-t", "22", "dev"])


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
    # Regression: a shared firmware_opts parent let write-recovery's --bkp default
    # leak into install/fetch via mutated argparse action defaults.
    assert _capture_bundle(monkeypatch, [cmd, "dev"]) == expected


def test_bundle_type_overrides(monkeypatch):
    assert _capture_bundle(monkeypatch, ["install", "--bkp", "dev"]) == "bkp"
    assert _capture_bundle(monkeypatch, ["write-recovery", "--update", "dev"]) == "update"


def test_install_signed_and_unsigned_are_mutually_exclusive(monkeypatch):
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, ["install", "--signed", "--unsigned", "dev"])


def test_install_via_http_with_no_install_errors(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, ["install", "--via-http", "--no-install", "dev"])
    assert exc.value.code == 2


def test_help_exits_zero_and_mentions_auto_install(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, ["--help"])
    assert exc.value.code == 0
    assert "auto-install" in capsys.readouterr().out


def test_command_registration_order(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, ["--help"])
    out = capsys.readouterr().out
    assert "{auto-install,cli,storage,install,fetch,write-recovery,install-onboard,wait,clean}" in out
