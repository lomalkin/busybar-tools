"""Tests for non-interactive command injection into `busybar cli`."""
import types

import pytest

import io

import busybar_tools.commands.cli_terminal as cli_cmd
import busybar_tools.bsb_term as bsb_term
from busybar_tools.bsb_term import _prelude_bytes, _inject_prelude
from busybar_tools.errors import DeviceError
from busybar_tools.options import CliOptions, DeviceEndpoint


class FakeStdin:
    def __init__(self, isatty, data=""):
        self._isatty = isatty
        self._data = data

    def isatty(self):
        return self._isatty

    def read(self):
        return self._data


def _args(**kw):
    base = dict(endpoint=DeviceEndpoint("10.0.0.1", 23), verbose=False, wait_before=False,
                interactive=False, timeout=5, commands=())
    base.update(kw)
    return CliOptions(**base)


@pytest.fixture
def recorder(monkeypatch):
    """Record dispatch: which of run_session / _run_cli_batch was called."""
    calls = {"session": [], "batch": []}

    def fake_session(host, port, tcp_timeout=None, prelude=None):
        calls["session"].append({"prelude": prelude})

    def fake_batch(args, cmds):
        calls["batch"].append(list(cmds))
        return 0

    monkeypatch.setattr(cli_cmd, "ensure_device_reachable", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_cmd, "run_session", fake_session)
    monkeypatch.setattr(cli_cmd, "_run_cli_batch", fake_batch)
    return calls


# --- _prelude_bytes ---------------------------------------------------------

def test_prelude_bytes_multiline_crlf():
    assert _prelude_bytes("a\nb") == b"a\r\nb\r\n"


def test_prelude_bytes_appends_trailing_newline():
    assert _prelude_bytes("device_info") == b"device_info\r\n"


def test_prelude_bytes_empty():
    assert _prelude_bytes("") == b""


class _FakeSock:
    """Minimal socket stand-in: yields canned recv chunks, records sent bytes."""
    def __init__(self, recv_chunks):
        self.sent = []
        self._recv = list(recv_chunks)

    def sendall(self, b):
        self.sent.append(b)

    def settimeout(self, t):
        pass

    def recv(self, n):
        return self._recv.pop(0) if self._recv else b""


def test_inject_prelude_waits_for_prompt_then_sends(monkeypatch):
    # Give stdout a .buffer (pytest capture replaces sys.stdout without one).
    monkeypatch.setattr(bsb_term.sys, "stdout", types.SimpleNamespace(buffer=io.BytesIO()))
    sock = _FakeSock([b"BUSY Bar banner\r\n>: "])

    _inject_prelude(sock, "device_info")

    # First elicits a prompt with CR, then injects the command once the prompt is seen.
    assert sock.sent[0] == b"\r"
    assert sock.sent[-1] == b"device_info\r\n"


def test_inject_prelude_noop_when_empty(monkeypatch):
    monkeypatch.setattr(bsb_term.sys, "stdout", types.SimpleNamespace(buffer=io.BytesIO()))
    sock = _FakeSock([b">: "])
    _inject_prelude(sock, "")
    assert sock.sent == []


# --- run_cli_terminal dispatch ---------------------------------------------

def test_args_with_i_and_tty_stays_interactive(monkeypatch, recorder):
    monkeypatch.setattr("sys.stdin", FakeStdin(isatty=True))
    cli_cmd.run_cli_terminal(_args(commands=("--", "device_info"), interactive=True))
    assert recorder["session"] == [{"prelude": "device_info"}]
    assert recorder["batch"] == []


def test_args_with_i_no_tty_falls_back_to_batch(monkeypatch, recorder):
    monkeypatch.setattr("sys.stdin", FakeStdin(isatty=False))
    cli_cmd.run_cli_terminal(_args(commands=("--", "device_info"), interactive=True))
    assert recorder["session"] == []
    assert recorder["batch"] == [["device_info"]]


def test_args_without_i_runs_batch(monkeypatch, recorder):
    monkeypatch.setattr("sys.stdin", FakeStdin(isatty=True))
    cli_cmd.run_cli_terminal(_args(commands=("--", "sysctl", "debug", "1")))
    assert recorder["session"] == []
    assert recorder["batch"] == [["sysctl debug 1"]]


def test_stdin_pipe_runs_batch_per_line(monkeypatch, recorder):
    monkeypatch.setattr("sys.stdin", FakeStdin(isatty=False, data="uptime\n\ndevice_info\n"))
    cli_cmd.run_cli_terminal(_args())
    assert recorder["session"] == []
    assert recorder["batch"] == [["uptime", "device_info"]]


def test_tty_no_args_is_interactive(monkeypatch, recorder):
    monkeypatch.setattr("sys.stdin", FakeStdin(isatty=True))
    cli_cmd.run_cli_terminal(_args())
    assert recorder["session"] == [{"prelude": None}]
    assert recorder["batch"] == []


# --- _run_cli_batch ---------------------------------------------------------

def test_run_cli_batch_sends_commands_in_order(monkeypatch, capsys):
    sent = []

    class FakeBSB:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cmd_oneshot(self, cmd, timeout=1):
            sent.append((cmd, timeout))
            return [f"out:{cmd}"]

    monkeypatch.setattr(cli_cmd, "BusybarCli", FakeBSB)
    ret = cli_cmd._run_cli_batch(_args(timeout=7), ["uptime", "device_info"])
    out = capsys.readouterr().out
    assert ret == 0
    assert sent == [("uptime", 7), ("device_info", 7)]
    assert "out:uptime" in out and "out:device_info" in out


def test_run_cli_batch_raises_device_error_on_failure(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            raise OSError("no device")

    monkeypatch.setattr(cli_cmd, "BusybarCli", Boom)
    with pytest.raises(DeviceError, match="CLI batch failed: no device"):
        cli_cmd._run_cli_batch(_args(), ["uptime"])


# --- Typer parsing ----------------------------------------------------------

def test_cli_i_dashdash_parses(monkeypatch):
    import sys
    from busybar_tools.cli import busybar_main
    import busybar_tools.presentation.device as device_cli

    captured = {}

    def fake(args):
        captured["interactive"] = args.interactive
        captured["cli_args"] = list(args.commands)
        return 0

    monkeypatch.setattr(device_cli, "run_cli_terminal", fake)
    monkeypatch.setattr(sys, "argv", ["busybar", "cli", "-i", "--", "device_info"])
    busybar_main()
    assert captured["interactive"] is True
    assert captured["cli_args"][-1] == "device_info"
