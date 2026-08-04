"""Unit tests for resolve_source local file/dir branches (no network)."""
import json
from busybar_tools.firmware import resolve_source
from busybar_tools.options import FirmwareSelection
import busybar_tools.firmware.source as source_module


def _args(source):
    return FirmwareSelection(source=source, target=22, signed=True)


def test_local_file_resolves_to_source_file(tmp_path):
    f = tmp_path / "bundle.tgz"
    f.write_text("x")
    source_file, source_dir = resolve_source(_args(str(f)))
    assert source_file == str(f)
    assert source_dir is None


def test_local_dir_resolves_to_source_dir(tmp_path):
    d = tmp_path / "unpacked"
    d.mkdir()
    source_file, source_dir = resolve_source(_args(str(d)))
    assert source_dir == str(d)
    assert source_file is None


def test_release_channel_resolves_from_directory_json(monkeypatch, tmp_path):
    bundle = tmp_path / "busybar-f21-update-0.10.2.tgz"
    bundle.write_text("bundle")
    directory = {
        "channels": [{
            "id": "release",
            "versions": [{
                "version": "0.10.2",
                "timestamp": 2,
                "files": [{
                    "url": "https://example/busybar-f21-update-0.10.2.tgz",
                    "target": "f21",
                    "type": "update_tgz",
                    "sha256": "expected",
                }],
            }],
        }],
    }

    monkeypatch.setattr(source_module, "workdir", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(source_module, "fetch_text", lambda *a, **k: json.dumps(directory))
    monkeypatch.setattr(source_module, "download_file_info", lambda *a, **k: str(bundle))

    source_file, source_dir = resolve_source(FirmwareSelection(
        source="release", target=21, signed=False,
    ))

    assert source_file == str(bundle)
    assert source_dir is None
