import shutil

from busybar_tools.cache import workdir
from busybar_tools.device import ensure_device_reachable
from busybar_tools.errors import BusybarError
from busybar_tools.options import WaitOptions


def run_wait_for_device(options: WaitOptions):
    ensure_device_reachable(options.endpoint, verbose=options.verbose)
    return 0


def run_clean():
    directory = workdir()
    print(f"Cleaning up {directory}...")

    try:
        shutil.rmtree(directory, ignore_errors=True)
    except Exception as e:
        raise BusybarError(f"Error cleaning up {directory}: {e}") from e

    return 0


__all__ = ["run_clean", "run_wait_for_device"]
