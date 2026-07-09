import logging
import shutil

from busybar_tools.device import wait_for_device_maybe
from busybar_tools.helpers import busybar_workdir_get


def run_wait_for_device(args):
    wait_for_device_maybe(args)


def run_clean(args):
    dir = busybar_workdir_get()
    print(f"Cleaning up {dir}...")

    try:
        shutil.rmtree(dir, ignore_errors=True)
    except Exception as e:
        logging.error(f"Error cleaning up {dir}: {e}")
        return 1

    return 0


__all__ = ["run_clean", "run_wait_for_device"]
