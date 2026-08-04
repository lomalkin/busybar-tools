"""Unit tests for run_factory_reset (device interaction mocked)."""
import types

import pytest

import busybar_tools as bt


class FakeBSB:
    def __init__(self, *a, **k):
        self.sent = []
        self.read = types.SimpleNamespace(until_timeout=lambda eol, timeout=None: self.drain_output)

    drain_output = b">: "

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def sysctl_debug(self, value):
        self.sent.append(f"sysctl debug {int(value)}\r")
        return []

    def send(self, line):
        self.sent.append(line)


def _args(**kw):
    base = dict(
        device="10.0.0.1", port=23, verbose=False, no_wait=True,
        shipping_mode=False, no_wait_after=False,
        offline_timeout=1, confirm_timeout=0,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


@pytest.fixture
def env(monkeypatch):
    """Fake BSB_Lite and silence countdown/sleep/pings; returns created instances."""
    instances = []

    def factory(*a, **k):
        bsb = FakeBSB(*a, **k)
        instances.append(bsb)
        return bsb

    waits = []
    monkeypatch.setattr(bt, "BSB_Lite", factory)
    monkeypatch.setattr(bt, "confirm_countdown", lambda action, seconds: None)
    monkeypatch.setattr(bt.time, "sleep", lambda s: None)
    monkeypatch.setattr(bt, "wait_for_device", lambda *a, **k: waits.append(k) or {"success": True})
    return {"instances": instances, "waits": waits}


def test_factory_reset_invokes_and_confirms(env):
    assert bt.run_factory_reset(_args()) == 0
    (bsb,) = env["instances"]
    assert "factory_reset\r" in bsb.sent
    assert "y\r" in bsb.sent
    # First waits for the device to drop offline, then to come back.
    assert env["waits"][0].get("success_ping_as") is False
    assert len(env["waits"]) == 2


def test_factory_reset_shipping_mode(env):
    assert bt.run_factory_reset(_args(shipping_mode=True)) == 0
    (bsb,) = env["instances"]
    assert "factory_reset -s\r" in bsb.sent


def test_factory_reset_aborts_when_not_allowed(env, monkeypatch):
    monkeypatch.setattr(FakeBSB, "drain_output", b"Factory reset is not allowed: battery low\r\n")
    assert bt.run_factory_reset(_args()) == 1
    (bsb,) = env["instances"]
    assert "y\r" not in bsb.sent


def test_factory_reset_no_wait_after_skips_pings(env):
    assert bt.run_factory_reset(_args(no_wait_after=True)) == 0
    assert env["waits"] == []


def test_factory_reset_reports_connection_failure(env, monkeypatch):
    def boom(*a, **k):
        raise OSError("no device")

    monkeypatch.setattr(bt, "BSB_Lite", boom)
    assert bt.run_factory_reset(_args()) == 1
