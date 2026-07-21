"""Firmware bundle transfer and verification over the device storage protocol."""

import logging
import os
import posixpath
import time

from busybar_tools.config import DIR_BSB_RECOVERY, DIR_BSB_TMP_UPDATE
from busybar_tools.device.cli import BusybarCli
from busybar_tools.device.operations import ensure_device_reachable
from busybar_tools.device.storage import DeviceStorage
from busybar_tools.errors import StorageError
from busybar_tools.options import DeviceEndpoint


def _mkdir_p(storage, path):
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = "/" + path
    current = ""
    for part in path.split("/"):
        if not part:
            current = "/"
            continue
        current = "/" + part if current == "/" else current + "/" + part
        if not storage.exist_dir(current):
            logging.info("Creating %s on device...", current)
            storage.mkdir(current)


def upload_directory(endpoint: DeviceEndpoint, source_dir, destination_dir, unlock_backup=False):
    try:
        if unlock_backup:
            with BusybarCli(endpoint.address) as cli:
                logging.info("Enabling debug mode and unlocking /bkp...")
                cli.cmd_oneshot("sysctl debug 1")
                cli.cmd_oneshot("sysctl storage_bkp_unlock 1")

        with DeviceStorage(endpoint.address) as storage:
            logging.info(
                "Uploading %s to %s @ %s:%s...",
                source_dir, destination_dir, endpoint.host, endpoint.port,
            )
            _mkdir_p(storage, destination_dir)
            for root, directories, files in os.walk(source_dir):
                for name in directories:
                    local_dir = os.path.join(root, name)
                    relative = os.path.relpath(local_dir, source_dir).replace(os.sep, "/")
                    _mkdir_p(storage, f"{destination_dir}/{relative}")
                for name in files:
                    local_file = os.path.join(root, name)
                    relative = os.path.relpath(local_file, source_dir).replace(os.sep, "/")
                    device_file = f"{destination_dir}/{relative}"
                    parent = posixpath.dirname(device_file)
                    if parent:
                        _mkdir_p(storage, parent)
                    logging.info("Uploading %s (%s bytes) to device...", device_file, os.path.getsize(local_file))
                    storage.send_file(local_file, device_file)
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError(f"Upload to {destination_dir} failed: {exc}") from exc
    finally:
        if unlock_backup:
            try:
                with BusybarCli(endpoint.address) as cli:
                    logging.info("Locking /bkp and disabling debug mode...")
                    cli.cmd_oneshot("sysctl storage_bkp_unlock 0")
                    cli.cmd_oneshot("sysctl debug 0")
            except Exception as exc:
                logging.warning("Could not restore /bkp lock state: %s", exc)


def verify_directory(endpoint: DeviceEndpoint, source_dir, destination_dir):
    try:
        with DeviceStorage(endpoint.address) as storage:
            logging.info("Verifying %s against %s...", destination_dir, source_dir)
            device_files = {}
            for root, _, files in storage.walk(destination_dir):
                for name in files:
                    path = os.path.join(root, name).replace(os.sep, "/")
                    relative = path.replace(destination_dir, "", 1).lstrip("/")
                    device_files[relative] = storage.size(path)

            mismatches = []
            for root, _, files in os.walk(source_dir):
                for name in files:
                    local_file = os.path.join(root, name)
                    relative = os.path.relpath(local_file, source_dir).replace(os.sep, "/")
                    local_size = os.path.getsize(local_file)
                    device_size = device_files.get(relative)
                    if device_size != local_size:
                        mismatches.append(f"{relative}: local={local_size}, device={device_size}")
                    else:
                        logging.info("%s: %s bytes", relative, local_size)
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError(f"Verification of {destination_dir} failed: {exc}") from exc
    if mismatches:
        raise StorageError("Verification failed after upload: " + "; ".join(mismatches))
    logging.info("All files verified successfully.")


def upload_bundle(
    endpoint: DeviceEndpoint,
    unpacked_bundle_dir,
    *,
    wait_before=True,
    verbose=True,
    save_as_recovery=False,
    warning_timeout=3,
):
    logging.info("Running update via storage...")
    destination = DIR_BSB_TMP_UPDATE
    if save_as_recovery:
        logging.warning("Danger! Saving update bundle as recovery bundle on device /bkp!")
        for remaining in range(warning_timeout, 0, -1):
            logging.warning("You have %s seconds to Cancel (Ctrl+C)...", remaining)
            time.sleep(1)
        destination = DIR_BSB_RECOVERY

    ensure_device_reachable(endpoint, enabled=wait_before, verbose=verbose)
    try:
        upload_directory(endpoint, unpacked_bundle_dir, destination, unlock_backup=save_as_recovery)
    except StorageError as exc:
        logging.warning("Upload did not complete cleanly: %s", exc)
        logging.warning("Continuing with device content verification...")
    verify_directory(endpoint, unpacked_bundle_dir, destination)
    return destination
