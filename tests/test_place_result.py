"""Unit tests for _place_result (fetch destination placement)."""
import os

import busybar_tools as bt


def test_no_output_returns_src_unchanged(tmp_path):
    f = tmp_path / "a.tgz"
    f.write_text("x")
    assert bt._place_result(str(f), None) == str(f)


def test_file_to_trailing_slash_dir(tmp_path):
    f = tmp_path / "a.tgz"
    f.write_text("x")
    out = tmp_path / "dst"
    res = bt._place_result(str(f), str(out) + os.sep)
    assert res == str(out / "a.tgz")
    assert os.path.isfile(res)


def test_file_to_existing_dir(tmp_path):
    f = tmp_path / "a.tgz"
    f.write_text("x")
    out = tmp_path / "dst"
    out.mkdir()
    res = bt._place_result(str(f), str(out))
    assert res == str(out / "a.tgz")
    assert os.path.isfile(res)


def test_file_to_explicit_filename_creates_parents(tmp_path):
    f = tmp_path / "a.tgz"
    f.write_text("x")
    dst = tmp_path / "sub" / "renamed.tgz"
    res = bt._place_result(str(f), str(dst))
    assert res == str(dst)
    assert os.path.isfile(dst)


def test_dir_copied_to_output(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("y")
    out = tmp_path / "out"
    res = bt._place_result(str(src), str(out))
    assert res == str(out)
    assert os.path.isfile(out / "f.txt")
