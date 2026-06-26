"""Live-device tests: inject commands into `cli` via several paths and read the response.

Read-only only (device_info / uptime) — nothing that mutates device state or reboots.
Run with: pytest --run-hardware [--device IP] [--port N]

NOTE: the interactive `-i` prelude path (busybar cli -i -- ...) is not auto-tested here —
it requires a real TTY and an interactive loop; verify it manually.
"""
import io

import busybar_tools as bt


def test_device_read_info_returns_complete(live_device):
    host, port = live_device
    info = bt.device_read_info(
        host, port, retries=5, delay=1,
        required_keys=bt._VERSION_FIELDS + bt._DETECT_FIELDS,
    )
    assert info.get("u5_firmware_target")
    assert info.get("u5_firmware_commit")


def test_cli_args_form_runs_command(make_args, capsys):
    ret = bt.run_cli_terminal(make_args(cli_args=["--", "device_info"]))
    out = capsys.readouterr().out
    assert ret in (0, None)
    assert "u5_firmware_target" in out


def test_cli_stdin_form_runs_commands(make_args, monkeypatch, capsys):
    stdin = io.StringIO("device_info\nuptime\n")
    monkeypatch.setattr("sys.stdin", stdin)
    bt.run_cli_terminal(make_args())
    out = capsys.readouterr().out
    assert "u5_firmware_target" in out
    assert "Uptime" in out


def test_run_cli_batch_reads_response(make_args, capsys):
    ret = bt._run_cli_batch(make_args(), ["device_info"])
    out = capsys.readouterr().out
    assert ret == 0
    assert "u5_firmware_target" in out
