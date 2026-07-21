from __future__ import annotations

import logging
import os
import posixpath

from busybar_tools.device.storage import DeviceStorage, StorageProtocolError


class StorageTransfer:
    """Recursive local/device transfer operations built on DeviceStorage."""

    def __init__(self, storage: DeviceStorage):
        self.storage = storage
        self.logger = logging.getLogger("busybar.storage")

    def send_file(self, device_file_path: str, local_file_path: str, force: bool = False) -> None:
        self.logger.debug(
            "Sending candidate %s -> %s (force=%s)",
            local_file_path,
            device_file_path,
            force,
        )
        do_upload = True
        if self.storage.exist_file(device_file_path) and not force:
            local_hash = self.storage.hash_local(local_file_path)
            device_hash = self.storage.hash_device(device_file_path)
            self.logger.debug("Hash check: local %s, device %s", local_hash, device_hash)
            do_upload = local_hash != device_hash

        if do_upload:
            self.logger.info('Sending "%s" to "%s"', local_file_path, device_file_path)
            self.storage.send_file(local_file_path, device_file_path)

    def make_path(self, device_dir_path: str) -> None:
        normalized = posixpath.normpath(device_dir_path)
        current = ""
        for part in normalized.split("/"):
            if not part:
                continue
            current += "/" + part
            if not self.storage.exist_dir(current):
                self.logger.debug('Directory "%s" does not exist; creating it', current)
                self.storage.mkdir(current)

    def recursive_send(self, device_path: str, local_path: str, force: bool = False) -> None:
        if not os.path.exists(local_path):
            raise StorageProtocolError(f'"{local_path}" does not exist')

        if not os.path.isdir(local_path):
            self.make_path(posixpath.dirname(device_path))
            self.send_file(device_path, local_path, force)
            return

        self.make_path(device_path)
        for directory_path, directory_names, filenames in os.walk(local_path):
            self.logger.debug('Processing directory "%s"', os.path.normpath(directory_path))
            directory_names.sort()
            filenames.sort()
            relative_path = os.path.relpath(directory_path, local_path)

            for directory_name in directory_names:
                target_dir = os.path.join(device_path, relative_path, directory_name)
                target_dir = os.path.normpath(target_dir).replace(os.sep, "/")
                self.make_path(target_dir)

            for filename in filenames:
                target_file = os.path.join(device_path, relative_path, filename)
                target_file = os.path.normpath(target_file).replace(os.sep, "/")
                local_file = os.path.normpath(os.path.join(directory_path, filename))
                self.send_file(target_file, local_file, force)

    def recursive_receive(self, device_path: str, local_path: str) -> None:
        if not self.storage.exist_dir(device_path):
            self.logger.info('Receiving "%s" to "%s"', device_path, local_path)
            self.storage.receive_file(device_path, local_path)
            return

        for directory_path, directory_names, filenames in self.storage.walk(device_path):
            self.logger.debug(
                'Processing directory "%s"',
                os.path.normpath(directory_path).replace(os.sep, "/"),
            )
            directory_names.sort()
            filenames.sort()
            relative_path = os.path.relpath(directory_path, device_path)

            for directory_name in directory_names:
                local_dir = os.path.normpath(
                    os.path.join(local_path, relative_path, directory_name)
                )
                os.makedirs(local_dir, exist_ok=True)

            for filename in filenames:
                local_file = os.path.normpath(
                    os.path.join(local_path, relative_path, filename)
                )
                device_file = os.path.normpath(
                    os.path.join(directory_path, filename)
                ).replace(os.sep, "/")
                self.logger.info('Receiving "%s" to "%s"', device_file, local_file)
                self.storage.receive_file(device_file, local_file)


__all__ = ["StorageTransfer"]
