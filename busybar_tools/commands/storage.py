from __future__ import annotations

import filecmp
import logging
import os
import posixpath
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, List

from busybar_tools.config import DIR_BSB_RECOVERY, DIR_BSB_TMP_UPDATE
from busybar_tools.device import BusybarCli, ensure_device_reachable
from busybar_tools.device.storage import DeviceStorage
from busybar_tools.errors import BusybarError, StorageError
from busybar_tools.options import DeviceEndpoint


@dataclass(frozen=True)
class StorageService:
    """Application operations for the device storage protocol."""

    endpoint: DeviceEndpoint
    wait_before: bool = True
    verbose: bool = True

    def _prepare(self) -> None:
        ensure_device_reachable(
            self.endpoint,
            enabled=self.wait_before,
            verbose=self.verbose,
        )

    @contextmanager
    def _open(self) -> Iterator[DeviceStorage]:
        self._prepare()
        try:
            with DeviceStorage(self.endpoint.address) as storage:
                yield storage
        except BusybarError:
            raise
        except Exception as exc:
            raise StorageError(f"Storage operation failed: {exc}") from exc

    def mkdir(self, device_path: str) -> None:
        with self._open() as storage:
            storage.mkdir(device_path)

    def format_external(self) -> None:
        with self._open() as storage:
            storage.format_ext()

    def remove(self, device_path: str) -> None:
        with self._open() as storage:
            storage.remove(device_path)

    def read(self, device_path: str) -> bytes:
        with self._open() as storage:
            return bytes(storage.read_file(device_path))

    def size(self, device_path: str) -> int:
        with self._open() as storage:
            return storage.size(device_path)

    def receive(self, device_path: str, local_path: str) -> None:
        with self._open() as storage:
            storage.recursive_receive(device_path, local_path)

    def send(self, local_path: str, device_path: str, force: bool = False) -> None:
        with self._open() as storage:
            storage.recursive_send(device_path, local_path, force)

    def list(self, device_path: str = "/") -> List[str]:
        with self._open() as storage:
            return list(storage.iter_tree(device_path))

    def stress(self, device_path: str, file_size: int, count: int, *, allow_internal: bool = False) -> None:
        if file_size < 0:
            raise StorageError("File size must not be negative")
        if count < 1:
            raise StorageError("Iteration count must be positive")
        if device_path.startswith(("/int", "/any")) and not allow_internal:
            raise StorageError("Internal storage stress test requires explicit confirmation")

        with tempfile.TemporaryDirectory() as tmpdirname:
            send_file = os.path.join(tmpdirname, "send")
            receive_file = os.path.join(tmpdirname, "receive")
            with open(send_file, "wb") as output:
                output.write(b"A" * file_size)

            with self._open() as storage:
                if storage.exist_file(device_path):
                    raise StorageError(f'File already exists: "{device_path}"')
                try:
                    for iteration in range(1, count + 1):
                        logging.info("Storage stress iteration %s of %s", iteration, count)
                        storage.send_file(send_file, device_path)
                        storage.receive_file(device_path, receive_file)
                        if not filecmp.cmp(receive_file, send_file, shallow=False):
                            raise StorageError(f"Files mismatch on iteration {iteration}")
                        storage.remove(device_path)
                        os.unlink(receive_file)
                finally:
                    if storage.exist_file(device_path):
                        storage.remove(device_path)


def _mkdir_p(storage, path):
    path = posixpath.normpath(path)
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
                    relative = os.path.relpath(os.path.join(root, name), source_dir).replace(os.sep, "/")
                    _mkdir_p(storage, f"{destination_dir}/{relative}")
                for name in files:
                    local_file = os.path.join(root, name)
                    relative = os.path.relpath(local_file, source_dir).replace(os.sep, "/")
                    device_file = f"{destination_dir}/{relative}"
                    _mkdir_p(storage, posixpath.dirname(device_file))
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
    destination = DIR_BSB_RECOVERY if save_as_recovery else DIR_BSB_TMP_UPDATE
    if save_as_recovery:
        logging.warning("Danger! Saving update bundle as recovery bundle on device /bkp!")
        for remaining in range(warning_timeout, 0, -1):
            logging.warning("You have %s seconds to Cancel (Ctrl+C)...", remaining)
            time.sleep(1)

    ensure_device_reachable(endpoint, enabled=wait_before, verbose=verbose)
    try:
        upload_directory(endpoint, unpacked_bundle_dir, destination, unlock_backup=save_as_recovery)
    except StorageError as exc:
        logging.warning("Upload did not complete cleanly: %s", exc)
        logging.warning("Continuing with device content verification...")
    verify_directory(endpoint, unpacked_bundle_dir, destination)
    return destination


__all__ = ["StorageService", "upload_bundle", "upload_directory", "verify_directory"]
