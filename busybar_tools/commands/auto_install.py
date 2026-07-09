import logging
import os

from busybar_tools.commands.install import run_install
from busybar_tools.device import (
    _DETECT_FIELDS,
    _VERSION_FIELDS,
    device_info_signed,
    device_info_target,
    device_read_info,
    device_version_fingerprint,
    format_version,
    wait_for_device_maybe,
)
from busybar_tools.helpers import wait_for_device


def run_auto_install(args):
    """High-level automatic install for regular users."""
    if os.path.isfile(args.source) or os.path.isdir(args.source):
        logging.error(
            f"auto-install works only with an update-server tag/branch or URL, not a local "
            f"file/directory ('{args.source}'). Use 'install' for a local source."
        )
        return 1

    wait_for_device_maybe(args)

    logging.info(f"Reading device info from {args.device}:{args.port}...")
    info_before = device_read_info(
        args.device, args.port,
        retries=5, delay=2, required_keys=_VERSION_FIELDS + _DETECT_FIELDS,
    )

    target = device_info_target(info_before)
    signed = device_info_signed(info_before)
    logging.info(
        f"Detected: target {target}, {'signed' if signed else 'unsigned'} firmware. "
        f"Current version: {format_version(info_before)}"
    )

    args.target = target
    args.signed = signed
    args.update_bundle_type = "update"
    args.invoke_update = True

    ret = run_install(args)
    if ret:
        return ret

    if getattr(args, "no_wait_after", False):
        logging.info("Skipping device reachability check after install (--no-wait-after).")
        return 0

    logging.info("Waiting for the device to reboot and come back...")
    wait_for_device(args.device, timeout=60, verbose=args.verbose, success_ping_as=False)
    wait_for_device(args.device, verbose=args.verbose)

    info_after = device_read_info(
        args.device, args.port,
        retries=20, delay=2, required_keys=_VERSION_FIELDS,
    )

    if device_version_fingerprint(info_before) == device_version_fingerprint(info_after):
        print(f"Already up to date - reinstalled the same build:\n  {format_version(info_after)}")
    else:
        print(f"Updated from:\n  {format_version(info_before)}\nto:\n  {format_version(info_after)}")
    print("Done. You are magnificent!")
    return 0


__all__ = ["run_auto_install"]
