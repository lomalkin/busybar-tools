"""BUSY Bar text CLI protocol client."""

from __future__ import annotations

import re

from busybar_tools.transport import DelimitedReader, TcpStream


def strip_ansi(data):
    ansi = re.compile(
        r'(?:\x1B[@-Z\\-_]|\x1B\[[0-?]*[ -/]*[@-~]|\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)|\x1B[P^_].*?\x1B\\)',
        re.DOTALL,
    )
    def clean(value):
        return ansi.sub("", value)

    if isinstance(data, str):
        return clean(data)
    if isinstance(data, tuple):
        return tuple(clean(value) for value in data)
    return [clean(value) for value in data]


def lines_clean(lines):
    return [line for line in strip_ansi(lines) if line.strip()]


def parse_kv(data, separator=":"):
    result = {}
    for line in data:
        if separator in line:
            key, value = line.split(separator, 1)
            result[key.strip()] = value.strip()
    return result


class BusybarCli:
    CLI_PROMPT_DEFAULT = ">: "
    CLI_EOL_DEFAULT = "\r\n"

    def __init__(self, address, chunk_size: int = 1024, handshake_timeout: float = 5):
        self.port = TcpStream(address, connect_timeout=handshake_timeout)
        self.read = DelimitedReader(self.port)
        self.chunk_size = chunk_size
        self.handshake_timeout = handshake_timeout
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
        self.send("\r")
        self.send("uptime\r")
        self.read.until_timeout("Uptime: ", timeout=self.handshake_timeout, timeout_assert=True)
        self.read.until_timeout(self.CLI_PROMPT, timeout=self.handshake_timeout, timeout_assert=True)

    def stop(self):
        self.port.close()

    def send(self, line: str):
        self.port.write(line.encode("ascii"))

    def read_until(self, delimiter: str = "\n", timeout: float = 0.1):
        return self.read.until_timeout(delimiter, timeout=timeout)

    def read_until_eol(self, timeout=None):
        return self.read_until(self.CLI_EOL, timeout=timeout)

    def read_until_prompt(self, timeout=None):
        return self.read_until(self.CLI_PROMPT, timeout=timeout)

    def status_lights(self, red, green, blue):
        if not all(0 <= value <= 255 for value in (red, green, blue)):
            raise ValueError("Status light values must be between 0 and 255")
        self.send(f"status_lights {red} {green} {blue}\r")
        return self.read_until_prompt(timeout=3).decode("utf-8", errors="replace").split(self.CLI_EOL)

    def device_info(self, timeout=6):
        self.send("device_info\r")
        lines = self.read_until_prompt(timeout=timeout).decode("utf-8", errors="replace").split(self.CLI_EOL)
        return parse_kv(lines)

    def cmd_oneshot(self, command: str, timeout=1):
        command = command.rstrip("\r\n")
        self.send(f"{command}\r")
        lines = self.read_until_prompt(timeout=timeout).decode("utf-8", errors="replace").split(self.CLI_EOL)
        return lines_clean([line for line in lines if line.strip() != command.strip()])

    def sysctl_debug(self, value: bool):
        return self.cmd_oneshot(f"sysctl debug {int(value)}", timeout=1)

    def cmd_sl_cli_enter(self, timeout=5):
        self.CLI_PROMPT = "917>: "
        return self.cmd_oneshot("sl_cli", timeout=timeout)

    def cmd_sl_cli_exit(self, timeout=2):
        self.CLI_PROMPT = self.CLI_PROMPT_DEFAULT
        return self.cmd_oneshot("exit", timeout=timeout)

    def cmd_interrupt(self, timeout=2):
        self.send("\x03")
        return self.read_until_prompt(timeout=timeout).decode("utf-8", errors="replace").split(self.CLI_EOL)
