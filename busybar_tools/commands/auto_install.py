import logging
import os

from busybar_tools.commands.install import run_install
from busybar_tools.device import (
    DETECT_FIELDS,
    VERSION_FIELDS,
    device_info_signed,
    device_info_target,
    device_version_fingerprint,
    ensure_device_reachable,
    format_version,
    read_device_info,
)
from busybar_tools.errors import FirmwareError
from busybar_tools.network import wait_for_device
from busybar_tools.options import AutoInstallOptions, FirmwareSelection, InstallOptions


def run_auto_install(options: AutoInstallOptions):
    """Autodetect the device and install the matching regular update."""
    if os.path.isfile(options.source) or os.path.isdir(options.source):
        raise FirmwareError(
            "auto-install works only with an update-server tag/branch or URL, not a local "
            f"file/directory ('{options.source}'). Use 'install' for a local source."
        )

    ensure_device_reachable(options.endpoint, enabled=options.wait_before, verbose=options.verbose)
    logging.info("Reading device info from %s:%s...", options.endpoint.host, options.endpoint.port)
    info_before = read_device_info(
        options.endpoint,
        retries=5,
        delay=2,
        required_keys=VERSION_FIELDS + DETECT_FIELDS,
    )

    target = device_info_target(info_before)
    signed = device_info_signed(info_before)
    logging.info(
        "Detected: target %s, %s firmware. Current version: %s",
        target,
        "signed" if signed else "unsigned",
        format_version(info_before),
    )

    install = InstallOptions(
        endpoint=options.endpoint,
        firmware=FirmwareSelection(options.source, target, "update", signed),
        wait_before=False,
        invoke_update=True,
        via_storage=options.via_storage,
        verbose=options.verbose,
    )
    run_install(install)

    if not options.wait_after:
        logging.info("Skipping device reachability check after install (--no-wait-after).")
        return 0

    logging.info("Waiting for the device to reboot and come back...")
    wait_for_device(options.endpoint.host, timeout=60, verbose=options.verbose, success_ping_as=False)
    wait_for_device(options.endpoint.host, verbose=options.verbose)
    info_after = read_device_info(
        options.endpoint,
        retries=20,
        delay=2,
        required_keys=VERSION_FIELDS,
    )

    if device_version_fingerprint(info_before) == device_version_fingerprint(info_after):
        print(f"Already up to date - reinstalled the same build:\n  {format_version(info_after)}")
    else:
        print(f"Updated from:\n  {format_version(info_before)}\nto:\n  {format_version(info_after)}")
    print("Done. You are magnificent!")
    return 0


__all__ = ["run_auto_install"]
