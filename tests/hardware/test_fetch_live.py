"""Live network tests: fetch really downloads/unpacks bundles from the update server.

Does not touch the device (only network + local disk). Guards the download / User-Agent path
and covers the fetch argument combinations. Run with: pytest --run-hardware (slow: real downloads).
"""
import os

import busybar_tools as bt


def _fetch_args(tmp_path, **over):
    base = dict(source="dev", target=22, signed=True, bundle_type="update",
                unpack=False, output=str(tmp_path) + os.sep)
    base.update(over)
    unpack = base.pop("unpack")
    output = base.pop("output")
    return bt.FetchOptions(bt.FirmwareSelection(**base), unpack=unpack, output=output)


def test_fetch_into_directory(tmp_path):
    ret = bt.run_fetch(_fetch_args(tmp_path))
    assert ret == 0
    files = [p for p in tmp_path.iterdir() if p.is_file()]
    assert files and files[0].stat().st_size > 0


def test_fetch_explicit_filename(tmp_path):
    dst = tmp_path / "my-bundle.tgz"
    ret = bt.run_fetch(_fetch_args(tmp_path, output=str(dst)))
    assert ret == 0
    assert dst.is_file() and dst.stat().st_size > 0


def test_fetch_unpack(tmp_path):
    out = tmp_path / "unpacked"
    ret = bt.run_fetch(_fetch_args(tmp_path, unpack=True, output=str(out)))
    assert ret == 0
    assert (out / "update.json").is_file()


def test_fetch_bkp_bundle(tmp_path):
    ret = bt.run_fetch(_fetch_args(tmp_path, bundle_type="bkp"))
    assert ret == 0
    files = [p for p in tmp_path.iterdir() if p.is_file()]
    assert files and files[0].stat().st_size > 0


def test_fetch_tag(tmp_path):
    ret = bt.run_fetch(_fetch_args(tmp_path, source="0.10.2"))
    assert ret == 0
    files = [p for p in tmp_path.iterdir() if p.is_file()]
    assert files and files[0].stat().st_size > 0
