import json
import logging

from busybar_tools.api import BusybarApiClient
from busybar_tools.config import DIR_BSB_RECOVERY, DIR_BSB_TMP_UPDATE
from busybar_tools.device import enable_debug, ensure_device_reachable, invoke_update
from busybar_tools.device.update_storage import upload_bundle
from busybar_tools.errors import FirmwareError
from busybar_tools.firmware import resolve_source, unpack_bundle
from busybar_tools.options import (
    InstallOnboardOptions,
    InstallOptions,
    WriteRecoveryOptions,
)


def run_install(options: InstallOptions):
    if options.verbose:
        logging.info("Install options: %s", options)

    source_file, source_dir = resolve_source(options.firmware)
    if source_file and not options.via_storage:
        return _update_via_http(options, source_file)
    if source_file:
        source_dir = unpack_bundle(source_file)
    if source_dir:
        return _install_from_directory(options, source_dir)
    return 0


def _install_from_directory(options: InstallOptions, source_dir: str):
    if not options.invoke_update:
        logging.warning("Will NOT invoke update after uploading the bundle on device!")

    update_dir = upload_bundle(
        options.endpoint,
        source_dir,
        wait_before=options.wait_before,
        verbose=options.verbose,
    )
    if options.invoke_update:
        return _update_from_storage(options.endpoint, update_dir, options.wait_before, options.verbose)
    return 0


def run_write_recovery(options: WriteRecoveryOptions):
    source_file, source_dir = resolve_source(options.firmware)
    if source_file is not None:
        source_dir = unpack_bundle(source_file)
    if not source_dir:
        raise FirmwareError("Could not obtain a bundle directory to write to recovery")

    upload_bundle(
        options.endpoint,
        source_dir,
        wait_before=options.wait_before,
        verbose=options.verbose,
        save_as_recovery=True,
        warning_timeout=options.confirm_timeout,
    )
    return 0


def _update_via_http(options: InstallOptions, source_file: str):
    logging.info("Using HTTP transport for update...")
    ensure_device_reachable(options.endpoint, enabled=options.wait_before, verbose=options.verbose)
    enable_debug(options.endpoint)

    last_percent = -1

    def progress(sent, total):
        nonlocal last_percent
        percent = int(sent * 100 / total) if total else 100
        if options.verbose and percent != last_percent:
            print(f"\rUpload via HTTP: {percent:3d}%", end="", flush=True)
            last_percent = percent

    api = BusybarApiClient(options.endpoint.host, port=80, timeout=60)
    body = api.upload_file("/api/update", source_file, progress=progress)
    if options.verbose and last_percent >= 0:
        print()
    if body:
        try:
            print(json.dumps(json.loads(body.decode("utf-8")), indent=4))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(body.decode(errors="replace"))
    return 0


def _update_from_storage(endpoint, update_dir, wait_before=True, verbose=True):
    logging.info("Running update via storage from %s...", update_dir)
    ensure_device_reachable(endpoint, enabled=wait_before, verbose=verbose)
    enable_debug(endpoint)
    invoke_update(endpoint, update_dir)
    return 0


def run_update_local(options: InstallOnboardOptions):
    target = options.device_path
    if target == "recovery":
        target = DIR_BSB_RECOVERY
    elif not target:
        target = DIR_BSB_TMP_UPDATE
    return _update_from_storage(
        options.endpoint,
        target,
        wait_before=options.wait_before,
        verbose=options.verbose,
    )


__all__ = ["run_install", "run_update_local", "run_write_recovery"]
