import os
import struct
import zlib

import busybar_tools.dfu.backends.dfu_util as dfu_util
from busybar_tools import dfu


def _make_dfuse(target_name="BUSY-f22", address=0x08012000, payload=b"abc"):
    prefix = b"DfuSe" + bytes([1]) + struct.pack("<I", 11 + 274 + 8 + len(payload)) + bytes([1])
    name = target_name.encode()[:255].ljust(255, b"\0")
    target_prefix = (
        b"Target"
        + bytes([0])
        + struct.pack("<I", 1)
        + name
        + struct.pack("<I", 8 + len(payload))
        + struct.pack("<I", 1)
    )
    return prefix + target_prefix + struct.pack("<II", address, len(payload)) + payload


def _with_dfu_suffix(data):
    suffix = struct.pack("<HHHH3sB", 0, 0xDF11, 0x0483, 0x011A, b"UFD", 16)
    crc = zlib.crc32(data + suffix) ^ 0xFFFFFFFF
    return data + suffix + struct.pack("<I", crc)


def test_resolve_recovery_dfu_accepts_local_dfu(tmp_path):
    f = tmp_path / "recovery.dfu"
    f.write_bytes(b"dfu")
    assert dfu.resolve_recovery_dfu(str(f), 22) == str(f)


def test_resolve_recovery_dfu_rejects_non_dfu_local_file(tmp_path):
    f = tmp_path / "recovery.bin"
    f.write_bytes(b"bin")
    try:
        dfu.resolve_recovery_dfu(str(f), 22)
    except RuntimeError as e:
        assert ".dfu" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_parse_dfuse_file(tmp_path):
    f = tmp_path / "recovery.dfu"
    f.write_bytes(_make_dfuse(target_name="BUSY-f22", address=0x08012000, payload=b"firmware"))

    image = dfu.parse_dfuse_file(str(f), expected_target="f22")

    assert image.target_name == "BUSY-f22"
    assert image.address == 0x08012000
    assert image.data == b"firmware"


def test_validate_recovery_image_accepts_valid_target_crc_and_flash_range(tmp_path):
    f = tmp_path / "recovery.dfu"
    f.write_bytes(_with_dfu_suffix(_make_dfuse(target_name="BUSY-f22", payload=b"firmware")))

    image = dfu.validate_recovery_image(str(f), 22)

    assert image.crc32_check is True


def test_dfu_util_program_command(monkeypatch, tmp_path):
    fw = tmp_path / "recovery.dfu"
    fw.write_bytes(b"dfu")
    calls = []
    monkeypatch.setattr(dfu_util.subprocess, "run", lambda cmd, **kwargs: calls.append((cmd, kwargs)))

    backend = dfu.DfuUtilBackend(executable=os.fspath(tmp_path / "dfu-util"))
    backend.program_firmware(str(fw))

    assert calls == [([backend.executable, "-d", "0483:df11", "-a", "0", "-D", str(fw)], {
        "check": True,
        "timeout": 180,
    })]


def test_dfu_util_leave_command(monkeypatch, tmp_path):
    calls = []
    removed = []

    class Result:
        returncode = 0
        stdout = ""

    def fake_run(cmd, *a, **k):
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(dfu_util.subprocess, "run", fake_run)
    monkeypatch.setattr(dfu_util.os, "unlink", lambda path: removed.append(path))

    backend = dfu.DfuUtilBackend(executable=os.fspath(tmp_path / "dfu-util"))
    backend.leave_dfu()

    assert len(calls) == 1
    assert calls[0][:7] == [backend.executable, "-d", "0483:df11", "-a", "0", "-s", "0x08000000:leave"]
    assert calls[0][7] == "-D"
    assert removed == [calls[0][8]]


def test_dfu_util_lists_and_selects_one_physical_device(monkeypatch, tmp_path):
    output = (
        'Found DFU: [0483:df11] ver=0200, devnum=5, cfg=1, intf=0, path="1-2", alt=0, '
        'name="Internal Flash", serial="ABC"\n'
        'Found DFU: [0483:df11] ver=0200, devnum=5, cfg=1, intf=0, path="1-2", alt=1, '
        'name="Option Bytes", serial="ABC"\n'
    ).encode()
    monkeypatch.setattr(dfu_util.subprocess, "check_output", lambda *args, **kwargs: output)

    backend = dfu.DfuUtilBackend(executable=os.fspath(tmp_path / "dfu-util"))
    devices = backend.list_devices()
    backend.select_device(devices[0])

    assert len(devices) == 1
    assert backend._selector_args() == ["-d", "0483:df11", "-S", "ABC"]


def test_dfu_util_leave_accepts_get_status_failure_after_submit(monkeypatch, tmp_path):
    class Result:
        returncode = 74
        stdout = "Submitting leave request...\nError during download get_status\n"

    monkeypatch.setattr(dfu_util.subprocess, "run", lambda *a, **k: Result())
    monkeypatch.setattr(dfu_util.os, "unlink", lambda path: None)

    backend = dfu.DfuUtilBackend(executable=os.fspath(tmp_path / "dfu-util"))
    backend.leave_dfu()


def test_install_dfu_util_uses_available_package_manager(monkeypatch):
    calls = []

    def fake_which(name):
        if name == "brew":
            return "/usr/bin/brew"
        if name == "dfu-util" and calls:
            return "/usr/local/bin/dfu-util"
        return None

    monkeypatch.setattr(dfu_util.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(dfu_util.shutil, "which", fake_which)
    monkeypatch.setattr(dfu_util.subprocess, "check_call", lambda cmd: calls.append(cmd))

    assert dfu.install_dfu_util() == "/usr/local/bin/dfu-util"
    assert calls == [["/usr/bin/brew", "install", "dfu-util"]]


def test_windows_install_dfu_util_prefers_scoop(monkeypatch):
    calls = []

    def fake_which(name):
        if name == "scoop.cmd":
            return "C:\\Users\\me\\scoop\\shims\\scoop.cmd"
        if name == "winget.exe":
            return "C:\\Windows\\System32\\winget.exe"
        if name == "dfu-util" and calls:
            return "C:\\Tools\\dfu-util.exe"
        return None

    monkeypatch.setattr(dfu_util.platform, "system", lambda: "Windows")
    monkeypatch.setattr(dfu_util.shutil, "which", fake_which)
    monkeypatch.setattr(dfu_util.subprocess, "check_call", lambda cmd: calls.append(cmd))

    assert dfu.install_dfu_util() == "C:\\Tools\\dfu-util.exe"
    assert calls == [[
        "C:\\Users\\me\\scoop\\shims\\scoop.cmd",
        "install",
        "dfu-util",
    ]]


def test_ensure_dfu_util_can_disable_auto_install(monkeypatch):
    monkeypatch.setattr(dfu_util.shutil, "which", lambda name: None)
    try:
        dfu.ensure_dfu_util(auto_install=False)
    except RuntimeError as e:
        assert "dfu-util was not found" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
