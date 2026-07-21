"""Shared TCP primitives for BUSY Bar text and storage protocols."""

from __future__ import annotations

import logging
import select
import socket
import time
from typing import Optional, Tuple

from busybar_tools.errors import DeviceError, DeviceProtocolError

logger = logging.getLogger(__name__)


class TcpStream:
    def __init__(self, address: Tuple[str, int], connect_timeout: float = 5):
        self.address, self.port = address
        self.connect_timeout = connect_timeout
        self.socket: Optional[socket.socket] = None
        self.transmitted = 0
        self.received = 0

    @property
    def is_connected(self) -> bool:
        return self.socket is not None

    def open(self):
        logger.debug("Connect to %s:%s", self.address, self.port)
        try:
            self.socket = socket.create_connection(
                (self.address, self.port),
                timeout=self.connect_timeout,
            )
        except OSError as exc:
            raise DeviceError(
                f"Could not connect to device at {self.address}:{self.port}: {exc}"
            ) from exc
        self.socket.settimeout(None)

    def close(self):
        if self.socket is not None:
            logger.debug("Disconnect from %s:%s", self.address, self.port)
            self.socket.close()
            self.socket = None

    def write(self, data: bytes):
        if self.socket is None:
            raise DeviceError("TCP stream is not connected")
        try:
            self.socket.sendall(data)
        except OSError as exc:
            self.close()
            raise DeviceError(f"Failed to write to the device TCP connection: {exc}") from exc
        self.transmitted += len(data)

    def read_exactly(self, size: int) -> bytes:
        if self.socket is None:
            raise DeviceError("TCP stream is not connected")
        data = bytearray()
        while len(data) < size:
            try:
                chunk = self.socket.recv(size - len(data))
            except OSError as exc:
                self.close()
                raise DeviceError(f"Failed to read from the device TCP connection: {exc}") from exc
            if not chunk:
                self.close()
                raise DeviceError("Device closed the TCP connection")
            data.extend(chunk)
            self.received += len(chunk)
        return bytes(data)

    def read_available(self, size: int, timeout: Optional[float] = 0) -> bytes:
        if self.socket is None:
            return b""
        readable, _, _ = select.select([self.socket], [], [], timeout)
        if not readable:
            return b""
        try:
            data = self.socket.recv(size)
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            self.close()
            return b""
        if not data:
            self.close()
            return b""
        self.received += len(data)
        return data

    def reset_input_buffer(self):
        while self.read_available(65536, timeout=0):
            pass

    @property
    def in_waiting(self):
        return 1


class DelimitedReader:
    def __init__(self, stream: TcpStream):
        self.buffer = bytearray()
        self.stream = stream

    def until(self, delimiter: str = "\n", cut_delimiter: bool = True) -> bytes:
        return self.until_timeout(delimiter, cut_delimiter=cut_delimiter)

    def until_timeout(
        self,
        delimiter: str = "\n",
        cut_delimiter: bool = True,
        timeout: Optional[float] = None,
        timeout_assert: bool = False,
    ) -> bytes:
        delimiter_bytes = delimiter.encode("ascii")
        deadline = time.monotonic() + timeout if timeout is not None else None
        while deadline is None or time.monotonic() < deadline:
            index = self.buffer.find(delimiter_bytes)
            if index >= 0:
                end = index if cut_delimiter else index + len(delimiter_bytes)
                result = bytes(self.buffer[:end])
                del self.buffer[: index + len(delimiter_bytes)]
                return result

            remaining = None if deadline is None else max(0, deadline - time.monotonic())
            poll_timeout = 0.1 if remaining is None else min(0.1, remaining)
            data = self.stream.read_available(max(1, self.stream.in_waiting), poll_timeout)
            if data:
                self.buffer.extend(data)
            elif not self.stream.is_connected:
                break

        result = bytes(self.buffer)
        self.buffer.clear()
        if timeout_assert:
            raise DeviceProtocolError(
                f'Timeout reached while waiting for device response "{delimiter}"'
            )
        return result
