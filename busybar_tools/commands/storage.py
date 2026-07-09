import logging
import subprocess
import sys

from busybar_tools.device import wait_for_device_maybe


def run_storage(args):
    wait_for_device_maybe(args)
    device_args = [
        "--host", args.device,
        "-p", str(args.port),
    ]
    storage_args = list(args.storage_args)
    if storage_args and storage_args[0] == "--":
        storage_args = storage_args[1:]
    cmd = [sys.executable, "-m", "busybar_tools.storage"] + device_args + storage_args
    logging.info(f"Invoking command: {' '.join(cmd)}")
    return subprocess.call(cmd)


__all__ = ["run_storage"]
