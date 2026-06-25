"""Unit tests for resolve_source local file/dir branches (no network)."""
import types

import busybar_tools as bt


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
