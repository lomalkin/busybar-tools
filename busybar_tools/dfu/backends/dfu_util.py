import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile

from busybar_tools.dfu.constants import DFU_PRODUCT_ID, DFU_VENDOR_ID
from busybar_tools.dfu.device import DfuDevice


class DfuUtilBackend:
    """Small wrapper around dfu-util."""

    UTIL_BIN_NAME = "dfu-util"
    def __init__(self, executable=None):
        self.executable = executable or shutil.which(self.UTIL_BIN_NAME)
        self.leave_status_uncertain = False
        self.selected_device = None

    def is_available(self):
        return bool(self.executable)

    def list_devices(self):
        if not self.is_available():
            return []
        try:
            result = subprocess.check_output(
                [self.executable, "--list"],
                stderr=subprocess.STDOUT,
                timeout=5,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Error executing {self.UTIL_BIN_NAME}: {e.output.decode(errors='replace')}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"{self.UTIL_BIN_NAME} --list timed out") from e
        except OSError as e:
            raise RuntimeError(f"Error executing {self.UTIL_BIN_NAME}: {e}") from e
        devices = {}
        pattern = re.compile(r"Found DFU:\s*\[([0-9a-f]{4}):([0-9a-f]{4})\](.*)", re.IGNORECASE)
        attribute = re.compile(r'(\w+)="([^"]*)"')
        for line in result.decode(errors="replace").splitlines():
            match = pattern.search(line)
            if not match:
                continue
            vendor_id, product_id = int(match.group(1), 16), int(match.group(2), 16)
            if vendor_id != DFU_VENDOR_ID or product_id != DFU_PRODUCT_ID:
                continue
            attrs = dict(attribute.findall(match.group(3)))
            serial = attrs.get("serial") or None
            path = attrs.get("path") or None
            key = f"serial:{serial}" if serial else f"path:{path}"
            devices.setdefault(key, DfuDevice(
                key=key,
                vendor_id=vendor_id,
                product_id=product_id,
                path=path,
                serial=serial,
                product=attrs.get("name") or None,
            ))
        return list(devices.values())

    def select_device(self, device):
        self.selected_device = device

    def _selector_args(self):
        args = ["-d", f"{DFU_VENDOR_ID:04x}:{DFU_PRODUCT_ID:04x}"]
        if self.selected_device is None:
            return args
        if self.selected_device.serial:
            return args + ["-S", self.selected_device.serial]
        if self.selected_device.path:
            return args + ["-p", self.selected_device.path]
        return args

    def program_firmware(self, fw_file, timeout=180):
        if not self.is_available():
            raise RuntimeError(
                "dfu-util was not found. Install dfu-util or provide it on PATH. "
                "Alternatively, use the default PyUSB backend."
            )
        cmd = [self.executable] + self._selector_args() + ["-a", "0", "-D", fw_file]
        logging.info(f"Flashing DFU firmware: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, timeout=timeout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"dfu-util failed with exit code {e.returncode}") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"dfu-util timed out after {timeout}s") from e

    def leave_dfu(self, address="0x08000000", timeout=15):
        if not self.is_available():
            raise RuntimeError("dfu-util was not found")

        if isinstance(address, int):
            address = f"0x{address:08x}"

        self.leave_status_uncertain = False
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="busybar_dfu_leave_", suffix=".bin", delete=False) as f:
                tmp_path = f.name

            cmd = [self.executable] + self._selector_args() + [
                "-a", "0", "-s", f"{address}:leave", "-D", tmp_path,
            ]
            logging.info(f"Leaving DFU mode: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                timeout=timeout,
            )
            if result.stdout:
                print(result.stdout, end="")
            if result.returncode == 0:
                return

            output = result.stdout or ""
            if "Submitting leave request" in output and "get_status" in output:
                self.leave_status_uncertain = True
                logging.info("DfuSe leave request was submitted; ignoring follow-up GETSTATUS failure.")
                return

            raise RuntimeError(f"dfu-util DfuSe leave failed with exit code {result.returncode}")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def _maybe_sudo(cmd):
    if platform.system() == "Windows":
        return cmd
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return cmd
    if shutil.which("sudo"):
        return ["sudo"] + cmd
    return cmd


def _install_candidates():
    system = platform.system()
    if system == "Windows":
        return [
            ("Scoop", ("scoop.cmd", "scoop.bat", "scoop.exe", "scoop"), ["install", "dfu-util"]),
            (
                "WinGet",
                ("winget.exe", "winget"),
                [
                    "install",
                    "--exact",
                    "--name",
                    "dfu-util",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
            ),
            ("Chocolatey", ("choco.exe", "choco.cmd", "choco.bat", "choco"), ["install", "dfu-util", "-y"]),
        ]
    if system == "Darwin":
        return [
            ("Homebrew", ("brew",), ["install", "dfu-util"]),
            ("MacPorts", ("port",), ["install", "dfu-util"]),
        ]
    return [
        ("APT", ("apt-get",), ["install", "-y", "dfu-util"]),
        ("DNF", ("dnf",), ["install", "-y", "dfu-util"]),
        ("YUM", ("yum",), ["install", "-y", "dfu-util"]),
        ("Pacman", ("pacman",), ["-S", "--noconfirm", "dfu-util"]),
        ("Zypper", ("zypper",), ["--non-interactive", "install", "dfu-util"]),
        ("APK", ("apk",), ["add", "dfu-util"]),
    ]


def dfu_util_install_hint():
    system = platform.system()
    if system == "Windows":
        return (
            "Install dfu-util with Scoop (`scoop install dfu-util`), "
            "WinGet (`winget install --exact --name dfu-util`), or Chocolatey (`choco install dfu-util -y`)."
        )
    if system == "Darwin":
        return "Install Homebrew and run `brew install dfu-util`."
    return "Install dfu-util with your package manager, for example `sudo apt-get install dfu-util`."


def install_dfu_util():
    """Install dfu-util using a common OS package manager, if one is available."""
    errors = []
    for name, executable_names, args in _install_candidates():
        executable = None
        for executable_name in executable_names:
            executable = shutil.which(executable_name)
            if executable:
                break
        if not executable:
            continue
        install_cmd = _maybe_sudo([executable] + args)
        logging.info(f"Installing dfu-util via {name}: {' '.join(install_cmd)}")
        try:
            subprocess.check_call(install_cmd)
        except subprocess.CalledProcessError as e:
            errors.append(f"{name} failed with exit code {e.returncode}")
            logging.warning(errors[-1])
            continue
        except OSError as e:
            errors.append(f"{name} failed to start: {e}")
            logging.warning(errors[-1])
            continue

        installed = shutil.which(DfuUtilBackend.UTIL_BIN_NAME)
        if installed:
            logging.info(f"dfu-util installed: {installed}")
            return installed
        errors.append(f"{name} completed, but dfu-util is still not on PATH")

    details = "; ".join(errors) if errors else "no supported package manager found"
    raise RuntimeError(f"Could not install dfu-util automatically ({details}). {dfu_util_install_hint()}")


def ensure_dfu_util(executable=None, auto_install=True):
    if executable:
        backend = DfuUtilBackend(executable)
        if backend.is_available():
            return backend
        raise RuntimeError(f"Specified dfu-util executable was not found: {executable}")

    backend = DfuUtilBackend()
    if backend.is_available():
        return backend

    if not auto_install:
        raise RuntimeError(f"dfu-util was not found. {dfu_util_install_hint()}")

    install_dfu_util()
    backend = DfuUtilBackend()
    if backend.is_available():
        return backend
    raise RuntimeError(f"dfu-util installation finished, but dfu-util was not found on PATH. {dfu_util_install_hint()}")
