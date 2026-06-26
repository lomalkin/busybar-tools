"""Live-device test: storage round-trip in a scratch dir (safe, cleans up).

Read/write only under /ext/tmp/bbtest; never touches firmware or /bkp. format_ext is NEVER tested.
Run with: pytest --run-hardware
"""
import busybar_tools as bt

DEV_DIR = "/ext/tmp/bbtest"
DEV_FILE = DEV_DIR + "/hello.txt"
CONTENT = b"busybar storage round-trip\n"


def _storage(make_args, *cmd, capfd):
    """Run `busybar storage -- <cmd>` and return (ret, stdout)."""
    ret = bt.run_storage(make_args(storage_args=["--", *cmd]))
    out = capfd.readouterr().out
    return ret, out


def test_storage_round_trip(make_args, tmp_path, capfd):
    local_in = tmp_path / "hello.txt"
    local_in.write_bytes(CONTENT)
    local_out = tmp_path / "back.txt"

    try:
        assert _storage(make_args, "mkdir", DEV_DIR, capfd=capfd)[0] == 0
        assert _storage(make_args, "send", str(local_in), DEV_FILE, capfd=capfd)[0] == 0

        ret, out = _storage(make_args, "list", DEV_DIR, capfd=capfd)
        assert ret == 0 and "hello.txt" in out

        ret, out = _storage(make_args, "size", DEV_FILE, capfd=capfd)
        assert ret == 0 and str(len(CONTENT)) in out

        assert _storage(make_args, "receive", DEV_FILE, str(local_out), capfd=capfd)[0] == 0
        assert local_out.read_bytes() == CONTENT

        ret, out = _storage(make_args, "read", DEV_FILE, capfd=capfd)
        assert ret == 0 and CONTENT.decode().strip() in out
    finally:
        _storage(make_args, "remove", DEV_FILE, capfd=capfd)
        _storage(make_args, "remove", DEV_DIR, capfd=capfd)
