from typing import Optional

import typer

from busybar_tools.commands.auto_install import run_auto_install
from busybar_tools.commands.fetch import run_fetch
from busybar_tools.commands.install import run_install, run_update_local, run_write_recovery
from busybar_tools.commands.recover import run_recover
from busybar_tools.config import DEVICE_IP, DEVICE_PORT, U5_TARGET_HW, UPDATE_DEFAULT_SOURCE
from busybar_tools.options import (
    AutoInstallOptions,
    FetchOptions,
    InstallOnboardOptions,
    InstallOptions,
    RecoveryOptions,
    WriteRecoveryOptions,
)
from busybar_tools.presentation.common import SOURCE_HELP, endpoint, finish, firmware_selection


def register(app):
    app.command("auto-install", help="Automatic install for regular users (autodetects target & signing)")(auto_install)
    app.command("recover", help="Recover STM32U5 firmware via USB DFU")(recover)
    app.command("install", help="Install firmware from an explicit source")(install)
    app.command("fetch", help="Download and optionally unpack a firmware bundle locally")(fetch)
    app.command("write-recovery", help="Write a firmware bundle into the recovery partition")(write_recovery)
    app.command("install-onboard", help="Install firmware already staged on the device")(install_onboard)


def auto_install(
    source: str = typer.Argument(UPDATE_DEFAULT_SOURCE, help=f"Update-server tag/branch or URL (default: {UPDATE_DEFAULT_SOURCE})"),
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
    no_wait_after: bool = typer.Option(False, "--no-wait-after", help="Skip waiting for the device to come back online after the operation"),
    via_storage: bool = typer.Option(True, "--via-storage/--via-http", help="Delivery transport"),
):
    return finish(run_auto_install(AutoInstallOptions(
        endpoint=endpoint(device, port), source=source, wait_before=not no_wait,
        wait_after=not no_wait_after, via_storage=via_storage,
    )))


def recover(
    source: str = typer.Argument("release", help="Update-server tag/branch or URL (default: release)"),
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    target: str = typer.Option("auto", "-t", "--target", help=f"Target hardware version, or 'auto' (fallback: {U5_TARGET_HW})"),
    file: Optional[str] = typer.Option(None, "--file", help="Use a local .dfu file instead of downloading from the update server"),
    backend: str = typer.Option("pyusb", "--backend", help="USB DFU backend: pyusb, dfu-util, or auto"),
    manual_dfu: bool = typer.Option(False, "--manual-dfu", help="Prompt for manual DFU mode instead of using the device CLI"),
    dfu_tool: Optional[str] = typer.Option(None, "--dfu-tool", help="Path to dfu-util executable when using dfu-util/auto backend"),
    no_install_dfu_tool: bool = typer.Option(False, "--no-install-dfu-tool", help="Fail instead of installing dfu-util for the dfu-util backend"),
    dfu_timeout: int = typer.Option(30, "--dfu-timeout", help="How long to wait for a DFU USB device"),
    wait_timeout: int = typer.Option(120, "--wait-timeout", help="How long to wait for the device to come back after flashing"),
    no_wait_after: bool = typer.Option(False, "--no-wait-after", help="Skip waiting for the device to come back online after flashing"),
):
    if backend not in ("pyusb", "dfu-util", "auto"):
        raise typer.BadParameter("--backend must be one of: pyusb, dfu-util, auto")
    return finish(run_recover(RecoveryOptions(
        endpoint=endpoint(device, port), source=source, target=target, file=file,
        backend=backend, manual_dfu=manual_dfu, dfu_tool=dfu_tool,
        install_dfu_tool=not no_install_dfu_tool, dfu_timeout=dfu_timeout,
        wait_timeout=wait_timeout, wait_after=not no_wait_after,
    )))


def install(
    source: str = typer.Argument(..., help=SOURCE_HELP),
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
    target: int = typer.Option(U5_TARGET_HW, "-t", "--target", help=f"Target hardware version, default: {U5_TARGET_HW}"),
    update: bool = typer.Option(False, "--update", help="Regular update bundle"),
    bkp: bool = typer.Option(False, "--bkp", help="Recovery bundle"),
    signed: bool = typer.Option(False, "--signed", help="Use signed firmware"),
    unsigned: bool = typer.Option(False, "--unsigned", help="Use unsigned firmware"),
    no_install: bool = typer.Option(False, "--no-install", help="Upload the bundle but do not install it"),
    via_storage: bool = typer.Option(True, "--via-storage/--via-http", help="Delivery transport"),
):
    if not via_storage and no_install:
        raise typer.BadParameter("--no-install requires --via-storage")
    selection = firmware_selection(source, target, update, bkp, signed, unsigned)
    return finish(run_install(InstallOptions(
        endpoint=endpoint(device, port), firmware=selection, wait_before=not no_wait,
        invoke_update=not no_install, via_storage=via_storage,
    )))


def fetch(
    source: str = typer.Argument(..., help=SOURCE_HELP),
    target: int = typer.Option(U5_TARGET_HW, "-t", "--target", help=f"Target hardware version, default: {U5_TARGET_HW}"),
    update: bool = typer.Option(False, "--update", help="Regular update bundle"),
    bkp: bool = typer.Option(False, "--bkp", help="Recovery bundle"),
    signed: bool = typer.Option(False, "--signed", help="Use signed firmware"),
    unsigned: bool = typer.Option(False, "--unsigned", help="Use unsigned firmware"),
    unpack: bool = typer.Option(False, "--unpack", help="Also unpack the downloaded bundle"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Destination directory or file path"),
):
    selection = firmware_selection(source, target, update, bkp, signed, unsigned)
    return finish(run_fetch(FetchOptions(selection, unpack=unpack, output=output)))


def write_recovery(
    source: str = typer.Argument(..., help=SOURCE_HELP),
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
    target: int = typer.Option(U5_TARGET_HW, "-t", "--target", help=f"Target hardware version, default: {U5_TARGET_HW}"),
    update: bool = typer.Option(False, "--update", help="Regular update bundle"),
    bkp: bool = typer.Option(False, "--bkp", help="Recovery bundle"),
    signed: bool = typer.Option(False, "--signed", help="Use signed firmware"),
    unsigned: bool = typer.Option(False, "--unsigned", help="Use unsigned firmware"),
    confirm_timeout: int = typer.Option(3, "--confirm-timeout", help="Countdown before overwriting recovery partition"),
):
    selection = firmware_selection(
        source, target, update, bkp, signed, unsigned,
        default_bundle="bkp", save_as_recovery=True,
    )
    return finish(run_write_recovery(WriteRecoveryOptions(
        endpoint=endpoint(device, port), firmware=selection,
        wait_before=not no_wait, confirm_timeout=confirm_timeout,
    )))


def install_onboard(
    device_path: str = typer.Argument("", help="On-device path to install from, or 'recovery'"),
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
):
    return finish(run_update_local(InstallOnboardOptions(
        endpoint=endpoint(device, port), device_path=device_path, wait_before=not no_wait,
    )))

