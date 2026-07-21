import logging

from busybar_tools.config import UPDATE_MANIFEST_FILE
from busybar_tools.console import print_pretty
from busybar_tools.device.cli import BusybarCli
from busybar_tools.errors import DeviceProtocolError
from busybar_tools.network import wait_for_device
from busybar_tools.options import DeviceEndpoint


def ensure_device_reachable(endpoint: DeviceEndpoint, enabled=True, verbose=True):
    if not enabled:
        logging.info("Skipping device reachability check (--no-wait).")
        return
    wait_for_device(endpoint.host, verbose=verbose)


def enable_debug(endpoint: DeviceEndpoint):
    logging.info("Enabling debug mode...")
    try:
        with BusybarCli(endpoint.address) as cli:
            print_pretty(cli.sysctl_debug(1))
    except Exception as exc:
        raise DeviceProtocolError(f"Failed to enable debug mode: {exc}") from exc


def invoke_update(endpoint: DeviceEndpoint, path: str):
    logging.info("Invoking update via device CLI...")
    try:
        with BusybarCli(endpoint.address) as cli:
            result = cli.cmd_oneshot(f"update install {path}/{UPDATE_MANIFEST_FILE}", timeout=3)
        print_pretty(result)
    except Exception as exc:
        raise DeviceProtocolError(f"Failed to invoke update: {exc}") from exc

