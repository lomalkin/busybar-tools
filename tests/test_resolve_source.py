"""Unit tests for resolve_source local file/dir branches (no network)."""
import json
import types

import busybar_tools as bt
import busybar_tools.firmware as firmware


def _args(source):
    return types.SimpleNamespace(
        source=source, target=22, signed=True, update_bundle_type="update"
    )


def test_local_file_resolves_to_source_file(tmp_path):
    f = tmp_path / "bundle.tgz"
    f.write_text("x")
    source_file, source_dir = bt.resolve_source(_args(str(f)))
    assert source_file == str(f)
    assert source_dir is None


def test_local_dir_resolves_to_source_dir(tmp_path):
    d = tmp_path / "unpacked"
    d.mkdir()
    source_file, source_dir = bt.resolve_source(_args(str(d)))
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

    def fail_index(*args, **kwargs):
        raise RuntimeError("404")

    monkeypatch.setattr(firmware, "busybar_get_index_by_url", fail_index)
    monkeypatch.setattr(firmware, "busybar_workdir_get", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(firmware, "fetch_url", lambda *a, **k: json.dumps(directory))
    monkeypatch.setattr(firmware, "file_download", lambda *a, **k: str(bundle))
    monkeypatch.setattr(firmware, "file_sha256", lambda *a, **k: "expected")

    source_file, source_dir = bt.resolve_source(types.SimpleNamespace(
        source="release",
        target=21,
        signed=False,
        update_bundle_type="update",
    ))

    assert source_file == str(bundle)
    assert source_dir is None
