"""Offline tests for the dfu package: DfuSe parsing/validation, resolver, dfu-util wrapper."""
import hashlib
import json
import os
import struct
import zlib

import pytest

from busybar_tools import dfu
import busybar_tools.dfu.backends.dfu_util as dfu_util
import busybar_tools.dfu.recovery as recovery
import busybar_tools.dfu.resolver as resolver

STM32_IDS = (0x0483, 0xDF11)


def _make_dfuse(
    target_name="BUSY-f22",
    address=0x08012000,
    payload=b"firmware",
    targets=1,
    nb_elements=1,
    with_suffix=True,
    suffix_ids=STM32_IDS,
    corrupt_crc=False,
):
    """Build a DfuSe file; defaults produce a valid single-target/single-element image."""
    name = target_name.encode()[:255].ljust(255, b"\0")
    element = struct.pack("<II", address, len(payload)) + payload
    target = (
        b"Target" + bytes([0]) + struct.pack("<I", 1) + name
        + struct.pack("<I", len(element)) + struct.pack("<I", nb_elements)
    )
    body = b"DfuSe" + bytes([1]) + struct.pack("<I", 11 + len(target) + len(element)) + bytes([targets])
    body += target + element
    if with_suffix:
        vendor_id, product_id = suffix_ids
        suffix = struct.pack("<HHHH", 0x0000, product_id, vendor_id, 0x011A) + b"UFD" + bytes([16])
        # dfu-util stores the raw (non-inverted) CRC-32 register.
        crc = (zlib.crc32(body + suffix) ^ 0xFFFFFFFF) & 0xFFFFFFFF
        if corrupt_crc:
            crc ^= 0x1
        body += suffix + struct.pack("<I", crc)
    return body


def _write_dfu(tmp_path, name="recovery.dfu", **kwargs):
    f = tmp_path / name
    f.write_bytes(_make_dfuse(**kwargs))
    return str(f)


# --- parse_dfuse_file --------------------------------------------------------

def test_parse_dfuse_file(tmp_path):
    path = _write_dfu(tmp_path)

    image = dfu.parse_dfuse_file(path, expected_target="f22")

    assert image.target_name == "BUSY-f22"
    assert image.address == 0x08012000
    assert image.data == b"firmware"


def test_parse_dfuse_rejects_target_mismatch(tmp_path):
    path = _write_dfu(tmp_path, target_name="BUSY-f21")
    with pytest.raises(RuntimeError, match="target mismatch"):
        dfu.parse_dfuse_file(path, expected_target="f22")


def test_parse_dfuse_rejects_corrupt_crc(tmp_path):
    path = _write_dfu(tmp_path, corrupt_crc=True)
    with pytest.raises(RuntimeError, match="CRC"):
        dfu.parse_dfuse_file(path)


def test_parse_dfuse_rejects_foreign_usb_ids(tmp_path):
    path = _write_dfu(tmp_path, suffix_ids=(0x1209, 0x0001))
    with pytest.raises(RuntimeError, match="USB IDs"):
        dfu.parse_dfuse_file(path)


def test_parse_dfuse_accepts_wildcard_usb_ids(tmp_path):
    path = _write_dfu(tmp_path, suffix_ids=(0xFFFF, 0xFFFF))
    assert dfu.parse_dfuse_file(path).data == b"firmware"


def test_parse_dfuse_without_suffix_parses_with_warning(tmp_path, caplog):
    path = _write_dfu(tmp_path, with_suffix=False, payload=b"firmware-long-enough-tail")
    image = dfu.parse_dfuse_file(path)
    assert image.data == b"firmware-long-enough-tail"
    assert any("No DFU suffix" in r.message for r in caplog.records)


def test_parse_dfuse_rejects_multiple_elements(tmp_path):
    path = _write_dfu(tmp_path, nb_elements=2)
    with pytest.raises(RuntimeError, match="elements"):
        dfu.parse_dfuse_file(path)


def test_parse_dfuse_rejects_multiple_targets(tmp_path):
    path = _write_dfu(tmp_path, targets=2)
    with pytest.raises(RuntimeError, match="targets"):
        dfu.parse_dfuse_file(path)


def test_parse_dfuse_rejects_non_dfuse(tmp_path):
    f = tmp_path / "x.dfu"
    f.write_bytes(b"\0" * 400)
    with pytest.raises(RuntimeError, match="Not a DfuSe"):
        dfu.parse_dfuse_file(str(f))


# --- resolve_recovery_dfu ----------------------------------------------------

def test_resolve_recovery_dfu_accepts_local_dfu(tmp_path):
    f = tmp_path / "recovery.dfu"
    f.write_bytes(b"dfu")
    assert dfu.resolve_recovery_dfu(str(f), 22) == str(f)


def test_resolve_recovery_dfu_rejects_non_dfu_local_file(tmp_path):
    f = tmp_path / "recovery.bin"
    f.write_bytes(b"bin")
    with pytest.raises(RuntimeError, match=r"\.dfu"):
        dfu.resolve_recovery_dfu(str(f), 22)


def test_resolver_integrity_error_does_not_fall_back(monkeypatch, tmp_path):
    # A hash-check failure must abort resolution, not degrade to the directory path.
    monkeypatch.setattr(resolver, "busybar_workdir_get", lambda sub: str(tmp_path))

    def integrity_boom(*a, **k):
        raise resolver.DfuIntegrityError("hash check failed")

    fallback_calls = []
    monkeypatch.setattr(resolver, "_download_index_match", integrity_boom)
    monkeypatch.setattr(resolver, "_download_directory_match", lambda *a, **k: fallback_calls.append(a))

    with pytest.raises(resolver.DfuIntegrityError):
        resolver.resolve_recovery_dfu("dev", 22)
    assert fallback_calls == []


def test_resolver_other_index_errors_fall_back_to_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(resolver, "busybar_workdir_get", lambda sub: str(tmp_path))

    def index_boom(*a, **k):
        raise RuntimeError("index not found")

    monkeypatch.setattr(resolver, "_download_index_match", index_boom)
    monkeypatch.setattr(resolver, "_download_directory_match", lambda *a, **k: "/x/recovery.dfu")

    assert resolver.resolve_recovery_dfu("release", 22) == "/x/recovery.dfu"


def _index_txt(payload):
    name = "busybar-f22-recovery-dev-31072026-4033f805.dfu"
    return name, f"{hashlib.sha256(payload).hexdigest()}  {name}\n"


def test_index_match_downloads_and_verifies(monkeypatch, tmp_path, caplog):
    payload = b"recovery-dfu-bytes"
    name, index = _index_txt(payload)
    monkeypatch.setattr(resolver, "fetch_url", lambda url, timeout=10: index)

    def fake_download(url, fname, work_dir, progress=False, timeout=60):
        path = os.path.join(work_dir, fname)
        with open(path, "wb") as f:
            f.write(payload)
        return path

    monkeypatch.setattr(resolver, "file_download", fake_download)
    with caplog.at_level("INFO"):
        path = resolver._download_index_match("https://upd/dev/", 22, str(tmp_path))
    assert path == os.path.join(str(tmp_path), name)
    assert any("Hash check passed" in r.message for r in caplog.records)


def test_index_match_hash_mismatch_is_integrity_error(monkeypatch, tmp_path):
    name, index = _index_txt(b"expected-content")
    monkeypatch.setattr(resolver, "fetch_url", lambda url, timeout=10: index)

    def fake_download(url, fname, work_dir, progress=False, timeout=60):
        path = os.path.join(work_dir, fname)
        with open(path, "wb") as f:
            f.write(b"tampered")
        return path

    monkeypatch.setattr(resolver, "file_download", fake_download)
    with pytest.raises(resolver.DfuIntegrityError):
        resolver._download_index_match("https://upd/dev/", 22, str(tmp_path))


def test_index_match_verifies_cached_file(monkeypatch, tmp_path, caplog):
    # A cache hit must still be hash-checked, and must not hit the network.
    payload = b"cached-recovery-dfu"
    name, index = _index_txt(payload)
    (tmp_path / name).write_bytes(payload)
    monkeypatch.setattr(resolver, "fetch_url", lambda url, timeout=10: index)

    def no_download(*a, **k):
        raise AssertionError("file_download must not be called for a valid cached file")

    monkeypatch.setattr(resolver, "file_download", no_download)
    with caplog.at_level("INFO"):
        path = resolver._download_index_match("https://upd/dev/", 22, str(tmp_path))
    assert path == str(tmp_path / name)
    assert any("Hash check passed" in r.message for r in caplog.records)


def _directory_json(sha256=None):
    file_info = {"type": "recovery_dfu", "target": "f22", "url": "https://upd/fw.dfu"}
    if sha256:
        file_info["sha256"] = sha256
    return json.dumps({"channels": [{"id": "release", "versions": [{"timestamp": 1, "files": [file_info]}]}]})


def test_directory_match_requires_sha256(monkeypatch, tmp_path):
    monkeypatch.setattr(resolver, "fetch_url", lambda url, timeout=10: _directory_json(sha256=None))
    with pytest.raises(RuntimeError, match="sha256"):
        resolver._download_directory_match("release", 22, str(tmp_path))


def test_directory_match_downloads_and_verifies(monkeypatch, tmp_path):
    payload = b"fw-bytes"
    monkeypatch.setattr(
        resolver, "fetch_url",
        lambda url, timeout=10: _directory_json(sha256=hashlib.sha256(payload).hexdigest()),
    )

    def fake_download(url, name, work_dir, progress=False, timeout=60):
        path = os.path.join(work_dir, name)
        with open(path, "wb") as f:
            f.write(payload)
        return path

    monkeypatch.setattr(resolver, "file_download", fake_download)
    path = resolver._download_directory_match("release", 22, str(tmp_path))
    assert path == os.path.join(str(tmp_path), "fw.dfu")


def test_directory_match_hash_mismatch_is_integrity_error(monkeypatch, tmp_path):
    monkeypatch.setattr(resolver, "fetch_url", lambda url, timeout=10: _directory_json(sha256="0" * 64))

    def fake_download(url, name, work_dir, progress=False, timeout=60):
        path = os.path.join(work_dir, name)
        with open(path, "wb") as f:
            f.write(b"tampered")
        return path

    monkeypatch.setattr(resolver, "file_download", fake_download)
    with pytest.raises(resolver.DfuIntegrityError):
        resolver._download_directory_match("release", 22, str(tmp_path))


def test_directory_match_rejects_unknown_source(tmp_path):
    with pytest.raises(RuntimeError, match="Cannot resolve"):
        resolver._download_directory_match("0.10.2", 22, str(tmp_path))


def test_directory_match_rejects_non_json_url(tmp_path):
    with pytest.raises(RuntimeError, match="directory.json"):
        resolver._download_directory_match("https://example.com/builds/dev/", 22, str(tmp_path))


# --- recovery backend selection ----------------------------------------------

def test_ensure_recovery_backend_rejects_unknown_name():
    with pytest.raises(RuntimeError, match="Unknown recovery backend"):
        recovery.ensure_recovery_backend("bogus")


def test_ensure_recovery_backend_auto_falls_back_to_dfu_util(monkeypatch):
    class Unavailable:
        def is_available(self):
            return False

    sentinel = object()
    monkeypatch.setattr(recovery, "PyUsbDfuSeBackend", Unavailable)
    monkeypatch.setattr(recovery, "ensure_dfu_util", lambda exe, auto_install: sentinel)
    assert recovery.ensure_recovery_backend("auto") is sentinel


# --- dfu-util wrapper ----------------------------------------------------------

def test_dfu_util_program_command(monkeypatch, tmp_path):
    fw = tmp_path / "recovery.dfu"
    fw.write_bytes(b"dfu")
    calls = []
    monkeypatch.setattr(dfu_util.subprocess, "check_call", lambda cmd: calls.append(cmd))

    backend = dfu.DfuUtilBackend(executable=os.fspath(tmp_path / "dfu-util"))
    backend.program_firmware(str(fw))

    # The device filter pins dfu-util to the STM32 bootloader IDs.
    assert calls == [[backend.executable, "-d", "0483:df11", "-a", "0", "-D", str(fw)]]


def test_dfu_util_program_command_can_reset(monkeypatch, tmp_path):
    fw = tmp_path / "recovery.dfu"
    fw.write_bytes(b"dfu")
    calls = []
    monkeypatch.setattr(dfu_util.subprocess, "check_call", lambda cmd: calls.append(cmd))

    backend = dfu.DfuUtilBackend(executable=os.fspath(tmp_path / "dfu-util"))
    backend.program_firmware(str(fw), reset=True)

    assert calls[0][-1] == "-R"


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
    assert calls[0][:7] == [backend.executable, "-d", "0483:df11", "-a", "0", "-s", "0x080fffff:leave"]
    assert calls[0][7] == "-D"
    assert removed == [calls[0][8]]


def test_dfu_util_leave_accepts_get_status_failure_after_submit(monkeypatch, tmp_path):
    class Result:
        returncode = 74
        stdout = "Submitting leave request...\nError during download get_status\n"

    monkeypatch.setattr(dfu_util.subprocess, "run", lambda *a, **k: Result())
    monkeypatch.setattr(dfu_util.os, "unlink", lambda path: None)

    backend = dfu.DfuUtilBackend(executable=os.fspath(tmp_path / "dfu-util"))
    backend.leave_dfu()
    assert backend.leave_status_uncertain


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
    assert calls == [["C:\\Users\\me\\scoop\\shims\\scoop.cmd", "install", "dfu-util"]]


def test_ensure_dfu_util_does_not_auto_install_by_default(monkeypatch):
    installs = []
    monkeypatch.setattr(dfu_util.shutil, "which", lambda name: None)
    monkeypatch.setattr(dfu_util.subprocess, "check_call", lambda cmd: installs.append(cmd))

    with pytest.raises(RuntimeError, match="dfu-util was not found"):
        dfu.ensure_dfu_util()
    assert installs == []
