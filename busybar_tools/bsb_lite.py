from __future__ import annotations

import socket, select
import time
import logging
import re

logger = logging.getLogger(__name__)

def strip_ansi(data):
    _ANSI_RE = re.compile(
        r'(?:\x1B[@-Z\\-_]|\x1B\[[0-?]*[ -/]*[@-~]|\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)|\x1B[P^_].*?\x1B\\)',
        re.DOTALL
    )
    clean = lambda s: _ANSI_RE.sub('', s)
    if isinstance(data, str):
        return clean(data)
    if isinstance(data, list):
        return [clean(s) for s in data]
    if isinstance(data, tuple):
        return tuple(clean(s) for s in data)
    # return data
    return [clean(s) for s in data]

def lines_clean(lines):
    lines = strip_ansi(lines)
    lines = [line for line in lines if line.strip()]    # remove empty
    return lines

def myrepr(obj):
    return repr(bytes(obj))

def parse_kv(data, separator=":"):
    res = {}
    for line in data:
        if line.find(":") != -1:
            kv = line.split(separator, 1)
            k = kv[0].strip()
            v = kv[1].strip()
            res[k] = v
    return res

class TCP_Stream:
    def __init__(self, portname: tuple[str, int]):
        self.address = portname[0]
        self.port = portname[1]
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.transmitted = 0
        self.received = 0
        self.is_connected = False

    def open(self):
        logger.debug(f"Connect to {self.address}:{self.port}")
        self.socket.connect((self.address, self.port))
        if self.socket.fileno() != -1:
            self.is_connected = True

    def __del__(self):
        self.close()

    def close(self):
        logger.debug(f"Disconnect from {self.address}:{self.port}")
        self.socket.close()
        self.is_connected = False

    def write(self, data: bytes):
        self.transmitted += len(data)
        logger.debug(f" <  {myrepr(data)}")
        self.socket.sendall(data)

    def try_read(self, size: int):
        data = self.socket.recv(size)
        self.received += len(data)
        return data
    
    def try_read_timeout(self, size: int):
        readable, _, _ = select.select([self.socket], [], [], 0)
        if readable:
            size = 1
            try:
                data = self.socket.recv(size)
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                # The device closed the connection abruptly (e.g. it rebooted
                # right after we invoked the update). On Windows this surfaces
                # as WinError 10054/10053 instead of a graceful EOF/timeout as
                # on Unix. Treat it as end-of-stream so the caller times out
                # gracefully with whatever was already buffered.
                self.is_connected = False
                return None
            self.received += len(data)
            # print(f"Received: {data}")
            return data
        return None

    def read(self, size: int):
        data = self.try_read(size)
        while len(data) < size:
            data += self.try_read(size - len(data))
        return data
    
    def read_timeout(self, size: int, timeout: float = 0.1):
        timeout = 0
        data = self.try_read_timeout(size)
        if data == None:
            data = b""
        ts = time.time()
        while len(data) < size and time.time() - ts < timeout:
            buf = self.try_read_timeout(size - len(data))
            if buf:
                data += buf
        return data
    
    def reset_input_buffer(self):
        pass
    
    @property
    def in_waiting(self):
        return 1

class BufferedRead:
    def __init__(self, stream: TCP_Stream):
        self.buffer = bytearray()
        self.stream = stream
    
    def until_timeout(self, eol: str = "\n", cut_eol: bool = True, timeout = None, timeout_assert = False):
        eol_bytes = eol.encode("ascii")
        ts = time.time()
        while time.time() - ts < timeout if timeout is not None else True:
            i = self.buffer.find(eol_bytes)
            if i >= 0:
                read = self.buffer[: i + len(eol_bytes)]
                logger.debug(f"  > {myrepr(read)}")
                if cut_eol:
                    read = self.buffer[:i]
                self.buffer = self.buffer[i + len(eol_bytes) :]
                return bytes(read)

            i = max(1, self.stream.in_waiting)
            data = self.stream.read_timeout(i, timeout=timeout)
            if data:
                self.buffer.extend(data)
            elif not self.stream.is_connected:
                # Connection dropped (e.g. device rebooted). Stop spinning and
                # return whatever we have buffered so far.
                break

        # Timeout reached, returning whatever is in the buffer
        ret = self.buffer
        logger.debug(f" W> {myrepr(ret)}")
        logger.warning(f"Timeout reached while waiting for \"{eol}\"")
        self.buffer = bytearray()
        
        # Assert
        if timeout is not None and timeout_assert:
            raise TimeoutError(f"Timeout reached while waiting for \"{eol}\". Check log file for details.")
        return bytes(ret)

class BSB_Lite():
    CLI_PROMPT_DEFAULT = ">: "
    CLI_EOL_DEFAULT = "\r\n"

    def __init__(self, portname: tuple[str, int], chunk_size: int = 1024):
        self.port = TCP_Stream(portname)
        self.read = BufferedRead(self.port)
        self.chunk_size = chunk_size
        self.CLI_PROMPT = self.CLI_PROMPT_DEFAULT
        self.CLI_EOL = self.CLI_EOL_DEFAULT

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def start(self):
        self.port.open()
        self.port.reset_input_buffer()
        # Send a command with a known syntax to make sure the buffer is flushed
        self.send("\r")
        self.send("uptime\r")
        self.read.until_timeout("Uptime: ", timeout=None)
        # And read buffer until we get prompt
        self.read.until_timeout(self.CLI_PROMPT, timeout=None)

    def stop(self) -> None:
        self.port.close()

    def send(self, line: str) -> None:
        self.port.write(line.encode("ascii"))

    def read_until(self, eol: str = "\n", timeout: float = 0.1):
        return self.read.until_timeout(eol = eol, timeout=timeout)
    
    def read_until_eol(self, timeout = None):
        return self.read_until(self.CLI_EOL, timeout=timeout)

    def read_until_prompt(self, timeout = None):
        return self.read_until(self.CLI_PROMPT, timeout=timeout)

    def status_lights(self, r, g, b):
        assert 0 <= r <= 255
        assert 0 <= g <= 255
        assert 0 <= b <= 255
        self.send(f"status_lights {r} {g} {b}\r")
        return self.read_until_prompt(timeout=None).decode("utf-8", errors="replace").split(self.CLI_EOL)

    def device_info(self, timeout=3*2):
        self.send("device_info\r")
        lines = self.read_until_prompt(timeout=timeout).decode("utf-8", errors="replace").split(self.CLI_EOL)
        return parse_kv(lines)

    def cmd_oneshot(self, cmd: str, timeout=1):
        self.send(f"{cmd}\r")
        lines = self.read_until_prompt(timeout=timeout).decode("utf-8", errors="replace").split(self.CLI_EOL)
        lines = [line for line in lines if line.strip() != cmd.strip()] # remove command itself
        lines = lines_clean(lines)
        return lines

    def sysctl_debug(self, value: bool):
        value = int(value)
        cmd = f"sysctl debug {value}\r"
        return self.cmd_oneshot(cmd, timeout=1)

    def cmd_sl_cli_enter(self, timeout=5):
        self.CLI_PROMPT = "917>: "
        return self.cmd_oneshot("sl_cli", timeout=timeout)

    def cmd_sl_cli_exit(self, timeout=2):
        self.CLI_PROMPT = self.CLI_PROMPT_DEFAULT
        return self.cmd_oneshot("exit", timeout=timeout)

    def cmd_interrupt(self, timeout=2):
        self.send("\x03")
        return self.read_until_prompt(timeout=timeout).decode("utf-8", errors="replace").split(self.CLI_EOL)

    # def cmd_sl_cli_wifi_rf_test_enter(self, timeout=5):
    #     self.CLI_PROMPT = "wifi_rf_test>: "
    #     return self.cmd_oneshot("wifi_rf_test", timeout=timeout)

    # def cmd_sl_cli_wifi_rf_test_exit(self, timeout=3):
    #     self.CLI_PROMPT = "917>: "
    #     return self.cmd_oneshot("exit", timeout=timeout)

    # def cmd_sl_cli_ble_per_test_enter(self, timeout=5):
    #     self.CLI_PROMPT = "ble_per>: "
    #     return self.cmd_oneshot("ble_per_test", timeout=timeout)

    # def cmd_sl_cli_ble_per_test_exit(self, timeout=3):
    #     self.CLI_PROMPT = "917>: "
    #     return self.cmd_oneshot("exit", timeout=timeout)
