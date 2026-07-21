"""Live-device test: storage round-trip in a scratch dir (safe, cleans up).

Read/write only under /ext/tmp/bbtest; never touches firmware or /bkp. format_ext is NEVER tested.
Run with: pytest --run-hardware
"""
from busybar_tools import StorageService

DEV_DIR = "/ext/tmp/bbtest"
DEV_FILE = DEV_DIR + "/hello.txt"
CONTENT = b"busybar storage round-trip\n"


def test_storage_round_trip(device_endpoint, tmp_path):
    local_in = tmp_path / "hello.txt"
    local_in.write_bytes(CONTENT)
    local_out = tmp_path / "back.txt"
    storage = StorageService(device_endpoint, wait_before=False)

    try:
        storage.mkdir(DEV_DIR)
        storage.send(str(local_in), DEV_FILE)
        assert any("hello.txt" in entry for entry in storage.list(DEV_DIR))
        assert storage.size(DEV_FILE) == len(CONTENT)
        storage.receive(DEV_FILE, str(local_out))
        assert local_out.read_bytes() == CONTENT
        assert storage.read(DEV_FILE) == CONTENT
    finally:
        storage.remove(DEV_FILE)
        storage.remove(DEV_DIR)
