"""Stable programmatic API for busybar-tools."""

from busybar_tools.commands.auto_install import run_auto_install
from busybar_tools.commands.cli_terminal import run_cli_terminal
from busybar_tools.commands.factory_reset import run_factory_reset
from busybar_tools.commands.fetch import run_fetch
from busybar_tools.commands.install import run_install, run_update_local, run_write_recovery
from busybar_tools.commands.recover import run_recover
from busybar_tools.commands.report import run_report
from busybar_tools.commands.storage import StorageService
from busybar_tools.commands.wait import run_clean, run_wait_for_device
from busybar_tools.device import (
    device_info_signed,
    device_info_target,
    device_version_fingerprint,
    format_version,
    read_device_info,
)
from busybar_tools.errors import BusybarError
from busybar_tools.options import (
    AutoInstallOptions,
    CliOptions,
    DeviceEndpoint,
    FactoryResetOptions,
    FetchOptions,
    FirmwareSelection,
    InstallOnboardOptions,
    InstallOptions,
    RecoveryOptions,
    WaitOptions,
    WriteRecoveryOptions,
)
from busybar_tools.report import ReportOptions

__all__ = [
    "AutoInstallOptions",
    "BusybarError",
    "CliOptions",
    "DeviceEndpoint",
    "FactoryResetOptions",
    "FetchOptions",
    "FirmwareSelection",
    "InstallOnboardOptions",
    "InstallOptions",
    "RecoveryOptions",
    "ReportOptions",
    "StorageService",
    "WaitOptions",
    "WriteRecoveryOptions",
    "device_info_signed",
    "device_info_target",
    "device_version_fingerprint",
    "format_version",
    "read_device_info",
    "run_auto_install",
    "run_clean",
    "run_cli_terminal",
    "run_factory_reset",
    "run_fetch",
    "run_install",
    "run_recover",
    "run_report",
    "run_update_local",
    "run_wait_for_device",
    "run_write_recovery",
]
