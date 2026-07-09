import logging

from busybar_tools.config import DIR_BSB_RECOVERY, DIR_BSB_TMP_UPDATE
from busybar_tools.device import (
    bsb_invoke_update,
    bsb_sysctl_debug_enable,
    wait_for_device_maybe,
)
from busybar_tools.firmware import resolve_source, unpack_bundle
from busybar_tools.storage_ops import (
    busybar_storage_upload_auto,
)
from busybar_tools.helpers import busybar_api_update


def run_install(args, verbose=False):
    if verbose:
        for arg, value in vars(args).items():
            print(f"\t{arg}: {value}")

    source_file, source_dir = resolve_source(args)
    args.source_file = source_file
    args.source_dir = source_dir

    if source_file:
        if args.via_storage is False:
            return run_update_via_http(args)
        source_dir = unpack_bundle(source_file)
        args.source_dir = source_dir

    if source_dir:
        return _install_from_dir(args, source_dir)

    return 0


def _install_from_dir(args, source_dir):
    invoke_update = args.invoke_update
    if invoke_update is False:
        logging.warning("Will NOT invoke update after uploading the bundle on device!")

    bsb_update_dst_dir = busybar_storage_upload_auto(args, source_dir)

    if invoke_update:
        return run_update_from_storage(args, bsb_update_dst_dir)
    return 0


def run_write_recovery(args):
    """Write a firmware bundle into the device recovery partition (/bkp), without installing it."""
    args.save_as_recovery = True
    source_file, source_dir = resolve_source(args)
    if source_file is not None:
        source_dir = unpack_bundle(source_file)

    if not source_dir:
        logging.error("Could not obtain a bundle directory to write to recovery.")
        return 1

    busybar_storage_upload_auto(args, source_dir, save_as_recovery=True, warning_timeout=args.confirm_timeout)
    return 0


def run_update_via_http(args):
    logging.info("Using HTTP transport for update...")
    wait_for_device_maybe(args)
    bsb_sysctl_debug_enable(args.device, args.port)
    return busybar_api_update(args.device, args.source_file)


def run_update_from_storage(args, update_dir):
    logging.info(f"Running update via storage from {update_dir}...")

    wait_for_device_maybe(args)

    assert bsb_sysctl_debug_enable(args.device, args.port), "Failed to enable debug mode!"
    assert bsb_invoke_update(args.device, args.port, update_dir), "Failed to invoke update via CLI!"

    return 0


def run_update_from_recovery(args):
    return run_update_from_storage(args, DIR_BSB_RECOVERY)


def run_update_local(args):
    target = args.device_path
    if target == "recovery":
        return run_update_from_recovery(args)
    if not target:
        target = DIR_BSB_TMP_UPDATE
    return run_update_from_storage(args, target)


__all__ = [
    "run_install",
    "run_update_from_recovery",
    "run_update_from_storage",
    "run_update_local",
    "run_update_via_http",
    "run_write_recovery",
]
