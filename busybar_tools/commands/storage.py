from __future__ import annotations

import filecmp
import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, List

from busybar_tools.device import ensure_device_reachable
from busybar_tools.device.storage import DeviceStorage
from busybar_tools.device.storage_transfer import StorageTransfer
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
            StorageTransfer(storage).recursive_receive(device_path, local_path)

    def send(self, local_path: str, device_path: str, force: bool = False) -> None:
        with self._open() as storage:
            StorageTransfer(storage).recursive_send(device_path, local_path, force)

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


__all__ = ["StorageService"]
