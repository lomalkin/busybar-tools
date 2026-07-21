#!/usr/bin/env python3
from __future__ import annotations

import enum
import hashlib
import logging
import math
import os
import sys
import time

from busybar_tools.errors import StorageError
from busybar_tools.transport import DelimitedReader, TcpStream


class StorageErrorCode(enum.Enum):
    OK = "OK"
    NOT_READY = "filesystem not ready"
    EXIST = "file/dir already exist"
    NOT_EXIST = "file/dir not exist"
    INVALID_PARAMETER = "invalid parameter"
    DENIED = "access denied"
    INVALID_NAME = "invalid name/path"
    INTERNAL = "internal error"
    NOT_IMPLEMENTED = "function not implemented"
    ALREADY_OPEN = "file is already open"
    UNKNOWN = "unknown error"

    @property
    def is_error(self):
        return self != self.OK

    @classmethod
    def from_value(cls, s: str | bytes):
        if isinstance(s, bytes):
            s = s.decode("ascii")
        for code in cls:
            if code.value == s:
                return code
        return cls.UNKNOWN


class StorageProtocolError(StorageError):
    def __init__(
        self,
        message: str,
        *,
        path: str = "",
        error_code: StorageErrorCode = StorageErrorCode.UNKNOWN,
    ):
        super().__init__(message)
        self.path = path
        self.error_code = error_code

    @classmethod
    def from_error_code(cls, path: str, error_code: StorageErrorCode):
        return cls(
            f"Storage error: path '{path}': {error_code.value}",
            path=path,
            error_code=error_code,
        )


class DeviceStorage:
    CLI_PROMPT = ">: "
    CLI_EOL = "\r\n"
    ALREADY_OPEN_RETRIES = 2
    RECONNECT_DELAY = 1.0
    POWER_ON_ANIMATION_DIR = "/bkp/recovery/resources/power_on/animations/"

    def __init__(self, portname: tuple[str, int], chunk_size: int = 200 * 1024, handshake_timeout: float = 5):
        self.port = TcpStream(portname, connect_timeout=handshake_timeout)
        self.read = DelimitedReader(self.port)
        self.chunk_size = chunk_size
        self.handshake_timeout = handshake_timeout

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def start(self):
        self.port.open()
        self.read.until_timeout(self.CLI_PROMPT, timeout=self.handshake_timeout, timeout_assert=True)
        self.port.reset_input_buffer()
        # Send a command with a known syntax to make sure the buffer is flushed
        self.send("uptime\r")
        self.read.until_timeout("Uptime: ", timeout=self.handshake_timeout, timeout_assert=True)
        # And read buffer until we get prompt
        self.read.until_timeout(self.CLI_PROMPT, timeout=self.handshake_timeout, timeout_assert=True)

    def stop(self) -> None:
        self.port.close()

    def send(self, line: str) -> None:
        self.port.write(line.encode("ascii"))

    def send_and_wait_eol(self, line: str):
        self.send(line)
        return self.read.until(self.CLI_EOL)

    def send_and_wait_prompt(self, line: str):
        self.send(line)
        return self.read.until(self.CLI_PROMPT)

    def has_error(self, data: bytes) -> bool:
        """Is data an error message"""
        return data.find(b"Storage error:") != -1

    def get_error(self, data: bytes) -> StorageErrorCode:
        """Extract a storage error code from a protocol response."""
        _, error_text = data.decode("ascii").split(": ")
        return StorageErrorCode.from_value(error_text.strip())

    def iter_tree(self, path: str = "/"):
        """Yield device paths and file sizes recursively."""
        path = path.replace("//", "/")

        self.send_and_wait_eol(f'storage list "{path}"\r')

        data = self.read.until(self.CLI_PROMPT)
        lines = data.split(b"\r\n")

        for line in lines:
            try:
                # TODO FL-3539: better decoding, considering non-ascii characters
                line = line.decode("ascii")
            except Exception:
                continue

            line = line.strip()

            if len(line) == 0:
                continue

            if self.has_error(line.encode("ascii")):
                raise StorageProtocolError.from_error_code(
                    path, self.get_error(line.encode("ascii"))
                )

            if line == "Empty":
                continue

            entry_type, info = line.split(" ", 1)
            if entry_type == "[D]":
                directory_path = (path + "/" + info).replace("//", "/")
                yield directory_path
                yield from self.iter_tree(directory_path)
            elif entry_type == "[F]":
                name, size = info.rsplit(" ", 1)
                yield (path + "/" + name).replace("//", "/") + ", size " + size

    def walk(self, path: str = "/"):
        dirs = []
        nondirs = []
        walk_dirs = []

        path = path.replace("//", "/")
        self.send_and_wait_eol(f'storage list "{path}"\r')
        data = self.read.until(self.CLI_PROMPT)
        lines = data.split(b"\r\n")

        for line in lines:
            try:
                # TODO FL-3539: better decoding, considering non-ascii characters
                line = line.decode("ascii")
            except Exception:
                continue

            line = line.strip()

            if len(line) == 0:
                continue

            if self.has_error(line.encode("ascii")):
                raise StorageProtocolError.from_error_code(
                    path, self.get_error(line.encode("ascii"))
                )

            if line == "Empty":
                continue

            entry_type, info = line.split(" ", 1)
            if entry_type == "[D]":
                # Print directory name
                dirs.append(info)
                walk_dirs.append((path + "/" + info).replace("//", "/"))

            elif entry_type == "[F]":
                name, size = info.rsplit(" ", 1)
                # Print file name and size
                nondirs.append(name)
            else:
                # Something wrong, pass
                pass

        # topdown walk, yield before recursing
        yield path, dirs, nondirs
        for new_path in walk_dirs:
            yield from self.walk(new_path)

    def send_file(self, filename_from: str, filename_to: str):
        """Send a local file to the device."""
        for attempt in range(self.ALREADY_OPEN_RETRIES + 1):
            try:
                self._send_file_once(filename_from, filename_to)
                return
            except StorageProtocolError as exc:
                if (
                    exc.error_code != StorageErrorCode.ALREADY_OPEN
                ):
                    raise
                if attempt == self.ALREADY_OPEN_RETRIES:
                    raise self._open_file_timeout_error(filename_to) from exc
                print()
                if attempt == 0:
                    logging.warning("Device still has %s open.", filename_to)
                    if filename_to.startswith(self.POWER_ON_ANIMATION_DIR):
                        logging.warning(
                            "The first-start animation is using this recovery file. "
                            "Press any button on BUSY Bar; upload will resume automatically."
                        )
                self._reconnect_after_interrupted_transfer()

    def _open_file_timeout_error(self, filename: str) -> StorageProtocolError:
        message = f"Device did not release '{filename}' after reconnecting"
        if filename.startswith(self.POWER_ON_ANIMATION_DIR):
            message += ". Press any button to close the first-start animation, then run write-recovery again"
        return StorageProtocolError(
            message,
            path=filename,
            error_code=StorageErrorCode.ALREADY_OPEN,
        )

    def _reconnect_after_interrupted_transfer(self) -> None:
        self.stop()
        self.read = DelimitedReader(self.port)
        time.sleep(self.RECONNECT_DELAY)
        self.start()

    def _send_file_once(self, filename_from: str, filename_to: str) -> None:
        with open(filename_from, "rb") as file:
            filesize = os.fstat(file.fileno()).st_size
            if self.exist_file(filename_to):
                self.remove(filename_to)

            buffer_size = self.chunk_size
            start_time = time.time()
            if filesize == 0:
                self._write_chunk(filename_to, b"")
                print()
                return

            while True:
                filedata = file.read(buffer_size)
                size = len(filedata)
                if size == 0:
                    break

                self._write_chunk(filename_to, filedata)

                ftell = file.tell()
                percent = math.ceil(ftell / filesize * 100)
                total_chunks = math.ceil(filesize / buffer_size)
                current_chunk = math.ceil(ftell / buffer_size)
                approx_speed = ftell / (time.time() - start_time + 0.0001)
                sys.stdout.write(
                    f"\r<{percent:3d}%, chunk {current_chunk:2d} of {total_chunks:2d} @ {approx_speed/1024:.2f} kb/s"
                )
                sys.stdout.flush()
        print()

    def _write_chunk(self, filename: str, data: bytes) -> None:
        self.send_and_wait_eol(f'storage write_chunk "{filename}" {len(data)}\r')
        answer = self.read.until(self.CLI_EOL)
        if self.has_error(answer):
            error_code = self.get_error(answer)
            self.read.until(self.CLI_PROMPT)
            raise StorageProtocolError.from_error_code(filename, error_code)
        if answer != b"Ready":
            self.read.until(self.CLI_PROMPT)
            raise StorageProtocolError(
                f"Unexpected response while opening '{filename}' for writing: "
                f"{answer.decode(errors='replace')!r}",
                path=filename,
            )

        if data:
            self.port.write(data)
        self.read.until(self.CLI_PROMPT)

    def read_file(self, filename: str):
        """Read a device file and return its bytes."""
        buffer_size = self.chunk_size
        start_time = time.time()
        self.send_and_wait_eol(
            'storage read_chunks "' + filename + '" ' + str(buffer_size) + "\r"
        )
        answer = self.read.until(self.CLI_EOL)
        filedata = bytearray()
        if self.has_error(answer):
            last_error = self.get_error(answer)
            self.read.until(self.CLI_PROMPT)
            raise StorageProtocolError.from_error_code(filename, last_error)
        size = int(answer.split(b": ")[1])
        read_size = 0

        while read_size < size:
            self.read.until("Ready?" + self.CLI_EOL)
            self.send("y")
            chunk_size = min(size - read_size, buffer_size)
            filedata.extend(self.port.read_exactly(chunk_size))
            read_size = read_size + chunk_size

            percent = math.ceil(read_size / size * 100)
            total_chunks = math.ceil(size / buffer_size)
            current_chunk = math.ceil(read_size / buffer_size)
            approx_speed = read_size / (time.time() - start_time + 0.0001)
            sys.stdout.write(
                f"\r>{percent:3d}%, chunk {current_chunk:2d} of {total_chunks:2d} @ {approx_speed/1024:.2f} kb/s"
            )
            sys.stdout.flush()
        print()
        self.read.until(self.CLI_PROMPT)
        return filedata

    def receive_file(self, filename_from: str, filename_to: str):
        """Receive a device file into local storage."""
        with open(filename_to, "wb") as file:
            data = self.read_file(filename_from)
            file.write(data)

    def exist(self, path: str):
        """Return whether a file or directory exists on the device."""
        self.send_and_wait_eol(f'storage stat "{path}"\r')
        response = self.read.until(self.CLI_EOL)
        self.read.until(self.CLI_PROMPT)

        return not self.has_error(response)

    def exist_dir(self, path: str):
        """Return whether a directory exists on the device."""
        self.send_and_wait_eol(f'storage stat "{path}"\r')
        response = self.read.until(self.CLI_EOL)
        self.read.until(self.CLI_PROMPT)
        if self.has_error(response):
            error_code = self.get_error(response)
            if error_code in (
                StorageErrorCode.NOT_EXIST,
                StorageErrorCode.INVALID_NAME,
            ):
                return False
            raise StorageProtocolError.from_error_code(path, error_code)

        return response == b"Directory" or response.startswith(b"Storage")

    def exist_file(self, path: str):
        """Return whether a file exists on the device."""
        self.send_and_wait_eol(f'storage stat "{path}"\r')
        response = self.read.until(self.CLI_EOL)
        self.read.until(self.CLI_PROMPT)

        return response.find(b"File, size:") != -1

    def _check_no_error(self, response, path=""):
        if self.has_error(response):
            raise StorageProtocolError.from_error_code(
                path, self.get_error(response)
            )

    def size(self, path: str):
        """Return the size of a device file."""
        self.send_and_wait_eol(f'storage stat "{path}"\r')
        response = self.read.until(self.CLI_EOL)
        self.read.until(self.CLI_PROMPT)

        self._check_no_error(response, path)
        if response.find(b"File, size:") != -1:
            size = int(
                "".join(
                    ch
                    for ch in response.split(b": ")[1].decode("ascii")
                    if ch.isdigit()
                )
            )
            return size
        raise StorageProtocolError("Not a file")

    def mkdir(self, path: str):
        """Create a directory on the device."""
        self.send_and_wait_eol(f'storage mkdir "{path}"\r')
        response = self.read.until(self.CLI_EOL)
        self.read.until(self.CLI_PROMPT)
        self._check_no_error(response, path)

    def format_ext(self):
        """Format external device storage."""
        self.send_and_wait_eol("storage format /ext\r")
        self.send_and_wait_eol("y\r")
        response = self.read.until(self.CLI_EOL)
        self.read.until(self.CLI_PROMPT)
        self._check_no_error(response, "/ext")

    def remove(self, path: str):
        """Remove a file or directory from the device."""
        self.send_and_wait_eol(f'storage remove "{path}"\r')
        response = self.read.until(self.CLI_EOL)
        self.read.until(self.CLI_PROMPT)
        self._check_no_error(response, path)

    def hash_local(self, filename: str):
        """Hash of local file"""
        hash_md5 = hashlib.md5()
        with open(filename, "rb") as f:
            for chunk in iter(lambda: f.read(self.chunk_size), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def hash_device(self, filename: str):
        """Return the MD5 hash of a device file."""
        self.send_and_wait_eol('storage md5 "' + filename + '"\r')
        digest = self.read.until(self.CLI_EOL)
        self.read.until(self.CLI_PROMPT)
        self._check_no_error(digest, filename)
        return digest.decode("ascii")
