from __future__ import annotations

import logging
import time

from busybar_tools.device import BusybarCli, ensure_device_reachable
from busybar_tools.errors import DeviceError
from busybar_tools.network import wait_for_device
from busybar_tools.options import FactoryResetOptions


def _drain(bsb: BusybarCli, seconds: float) -> bytes:
    return bsb.read.until_timeout("\x00", timeout=seconds)


def _factory_reset_command(shipping_mode: bool) -> str:
    return "factory_reset -s" if shipping_mode else "factory_reset"


def _invoke_factory_reset(device: str, port: int, shipping_mode: bool) -> None:
    command = _factory_reset_command(shipping_mode)
    with BusybarCli((device, port)) as bsb:
        logging.info("Enabling debug CLI commands...")
        bsb.send("sysctl debug 1\r")
        _drain(bsb, 1)

        logging.info("Invoking %s...", command)
        bsb.send(f"{command}\r")
        output = _drain(bsb, 1).decode("utf-8", errors="replace")
        if "Factory reset is not allowed" in output:
            raise RuntimeError(output.strip())

        logging.info("Confirming factory reset...")
        bsb.send("y\r")
        _drain(bsb, 3)
        time.sleep(1)


def run_factory_reset(options: FactoryResetOptions):
    """Perform a device factory reset via CLI, optionally entering shipping mode."""
    ensure_device_reachable(options.endpoint, enabled=options.wait_before, verbose=options.verbose)

    try:
        _invoke_factory_reset(options.endpoint.host, options.endpoint.port, options.shipping_mode)
    except Exception as exc:
        raise DeviceError(f"Failed to invoke factory reset: {exc}") from exc

    if not options.wait_after:
        logging.info("Skipping device reachability check after factory reset (--no-wait-after).")
        return 0

    logging.info("Waiting for the device to reboot...")
    wait_for_device(
        options.endpoint.host,
        timeout=options.offline_timeout,
        verbose=options.verbose,
        success_ping_as=False,
    )
    wait_for_device(options.endpoint.host, verbose=options.verbose)
    print("Factory reset complete.")
    return 0


__all__ = ["run_factory_reset"]
