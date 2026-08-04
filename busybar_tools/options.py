"""Typed inputs shared by the CLI and application command handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Union

from busybar_tools.config import DEVICE_IP, DEVICE_PORT


@dataclass(frozen=True)
class DeviceEndpoint:
    host: str = DEVICE_IP
    port: int = DEVICE_PORT

    @property
    def address(self) -> Tuple[str, int]:
        return self.host, self.port


@dataclass(frozen=True)
class FirmwareSelection:
    source: str
    target: int
    bundle_type: str = "update"
    signed: bool = True
    save_as_recovery: bool = False


@dataclass(frozen=True)
class AutoInstallOptions:
    endpoint: DeviceEndpoint
    source: str
    wait_before: bool = True
    wait_after: bool = True
    via_storage: bool = True
    verbose: bool = True


@dataclass(frozen=True)
class InstallOptions:
    endpoint: DeviceEndpoint
    firmware: FirmwareSelection
    wait_before: bool = True
    invoke_update: bool = True
    via_storage: bool = True
    verbose: bool = True


@dataclass(frozen=True)
class FetchOptions:
    firmware: FirmwareSelection
    unpack: bool = False
    output: Optional[str] = None


@dataclass(frozen=True)
class WriteRecoveryOptions:
    endpoint: DeviceEndpoint
    firmware: FirmwareSelection
    wait_before: bool = True
    confirm_timeout: int = 3
    verbose: bool = True


@dataclass(frozen=True)
class InstallOnboardOptions:
    endpoint: DeviceEndpoint
    device_path: str = ""
    wait_before: bool = True
    verbose: bool = True


@dataclass(frozen=True)
class RecoveryOptions:
    endpoint: DeviceEndpoint
    source: str = "release"
    target: Union[int, str] = "auto"
    file: Optional[str] = None
    backend: str = "pyusb"
    manual_dfu: bool = False
    dfu_tool: Optional[str] = None
    install_dfu_tool: bool = True
    dfu_timeout: int = 30
    flash_timeout: int = 180
    wait_timeout: int = 120
    wait_after: bool = True
    assume_yes: bool = False
    verbose: bool = True


@dataclass(frozen=True)
class CliOptions:
    endpoint: DeviceEndpoint
    wait_before: bool = True
    interactive: bool = False
    timeout: int = 5
    commands: Tuple[str, ...] = ()
    verbose: bool = True


@dataclass(frozen=True)
class FactoryResetOptions:
    endpoint: DeviceEndpoint
    wait_before: bool = True
    shipping_mode: bool = False
    wait_after: bool = True
    offline_timeout: int = 180
    verbose: bool = True


@dataclass(frozen=True)
class WaitOptions:
    endpoint: DeviceEndpoint
    verbose: bool = True
