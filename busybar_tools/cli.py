import logging
import sys
from importlib.metadata import version
from types import SimpleNamespace
from typing import Optional

import click
import typer

try:
    import typer.rich_utils
    typer.rich_utils.rich = None
except Exception:
    pass

from busybar_tools.commands.auto_install import run_auto_install
from busybar_tools.commands.cli_terminal import run_cli_terminal
from busybar_tools.commands.fetch import run_fetch
from busybar_tools.commands.install import run_install, run_update_local, run_write_recovery
from busybar_tools.commands.recover import run_recover
from busybar_tools.commands.report import run_report
from busybar_tools.commands.storage import run_storage
from busybar_tools.commands.wait import run_clean, run_wait_for_device
from busybar_tools.config import DEVICE_IP, DEVICE_IP_REF, DEVICE_PORT, U5_TARGET_HW, UPDATE_DEFAULT_SOURCE
from busybar_tools.helpers import setup_logging


__version__ = "unknown"
try:
    __version__ = version("busybar-tools")
except Exception:
    __version__ = "unknown"


TOP_EPILOG = """\
examples:
  busybar auto-install          autodetect & install the latest release firmware (recommended)
  busybar auto-install 0.10.2   install a specific tag

Most users want `busybar auto-install`. Other commands are explicit/low-level -
run `busybar <command> --help` for details.
"""

SOURCE_HELP = (
    "Firmware source. Accepted forms, in priority order: explicit URL (http/https), "
    "local bundle file, local directory, or update-server tag/branch."
)

COMMAND_HELP = [
    ("auto-install", "Automatic install for regular users (autodetects target & signing)"),
    ("cli", "CLI terminal session to the device"),
    ("recover", "Recover STM32U5 firmware via USB DFU"),
    ("report", "Collect a diagnostic report archive from the device"),
    ("storage", "Run the embedded storage.py utility on the device"),
    ("install", "Install firmware from an explicit source"),
    ("fetch", "Download and optionally unpack a firmware bundle locally"),
    ("write-recovery", "Write a firmware bundle into the recovery partition"),
    ("install-onboard", "Install firmware already staged on the device"),
    ("wait", "Wait for the device to be reachable via ping"),
    ("clean", "Clean the package tmp/cache directory"),
]


app = typer.Typer(
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Firmware installer and tooling for BUSY Bar devices.",
    epilog=TOP_EPILOG,
    invoke_without_command=True,
    no_args_is_help=True,
)


def _print_top_level_help():
    print("Usage: busybar [OPTIONS] COMMAND [ARGS]...")
    print()
    print("Firmware installer and tooling for BUSY Bar devices.")
    print()
    print("Options:")
    print("  --version              Show the busybar-tools version and exit.")
    print("  --install-completion   Install completion for the current shell.")
    print("  --show-completion      Show completion for the current shell.")
    print("  -h, --help             Show this message and exit.")
    print()
    print("Commands:")
    width = max(len(name) for name, _ in COMMAND_HELP)
    for name, description in COMMAND_HELP:
        print(f"  {name:<{width}}  {description}")
    print()
    print(TOP_EPILOG.strip())


def _device_option(value):
    if value.lower() in ("r", "ref"):
        return DEVICE_IP_REF
    return value


def _args(**kwargs):
    kwargs.setdefault("verbose", True)
    if "device" in kwargs and kwargs["device"]:
        kwargs["device"] = _device_option(kwargs["device"])
    return SimpleNamespace(**kwargs)


def _finish(ret):
    if ret and ret != 0:
        raise typer.Exit(int(ret))
    return ret or 0


def _bundle_type(update, bkp, default):
    if update and bkp:
        raise typer.BadParameter("--update and --bkp are mutually exclusive")
    if update:
        return "update"
    if bkp:
        return "bkp"
    return default


def _signed_value(signed, unsigned):
    if signed and unsigned:
        raise typer.BadParameter("--signed and --unsigned are mutually exclusive")
    if unsigned:
        return False
    return True


def _firmware_args(source, target, update, bkp, signed, unsigned, default_bundle="update"):
    return {
        "source": source,
        "target": target,
        "update_bundle_type": _bundle_type(update, bkp, default_bundle),
        "signed": _signed_value(signed, unsigned),
    }


@app.callback()
def _main_callback(
    version_flag: bool = typer.Option(
        False,
        "--version",
        help="Show the busybar-tools version and exit.",
        is_eager=True,
    ),
):
    if version_flag:
        typer.echo(f"busybar-tools {__version__}")
        raise typer.Exit()


@app.command("auto-install", help="Automatic install for regular users (autodetects target & signing)")
def auto_install(
    source: str = typer.Argument(UPDATE_DEFAULT_SOURCE, help=f"Update-server tag/branch or URL (default: {UPDATE_DEFAULT_SOURCE})"),
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
    no_wait_after: bool = typer.Option(False, "--no-wait-after", help="Skip waiting for the device to come back online after the operation"),
    via_storage: bool = typer.Option(True, "--via-storage/--via-http", help="Delivery transport"),
):
    """Autodetect target/signing, fetch matching update bundle, and install it."""
    return _finish(run_auto_install(_args(
        source=source,
        device=device,
        port=port,
        no_wait=no_wait,
        no_wait_after=no_wait_after,
        via_storage=via_storage,
    )))


@app.command("cli", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}, help="CLI terminal session to the device")
def cli_terminal(
    ctx: typer.Context,
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="After running command arguments, stay interactive"),
    timeout: int = typer.Option(5, "--timeout", help="Per-command response wait cap for non-interactive runs"),
):
    """Interactive CLI session, or run commands non-interactively after `--`."""
    return _finish(run_cli_terminal(_args(
        device=device,
        port=port,
        no_wait=no_wait,
        interactive=interactive,
        timeout=timeout,
        cli_args=list(ctx.args),
    )))


@app.command("recover", help="Recover STM32U5 firmware via USB DFU")
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
    return _finish(run_recover(_args(
        source=source,
        device=device,
        port=port,
        target=target,
        file=file,
        backend=backend,
        manual_dfu=manual_dfu,
        dfu_tool=dfu_tool,
        no_install_dfu_tool=no_install_dfu_tool,
        dfu_timeout=dfu_timeout,
        wait_timeout=wait_timeout,
        no_wait_after=no_wait_after,
    )))


@app.command("report", help="Collect a diagnostic report archive from the device")
def report(
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device CLI port, default: {DEVICE_PORT}"),
    http_port: int = typer.Option(80, "--http-port", help="Device HTTP API port, default: 80"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output .zip path"),
    api_token: Optional[str] = typer.Option(None, "--api-token", help="HTTP API token for devices with access key enabled"),
    timeout: int = typer.Option(5, "--timeout", help="HTTP request timeout in seconds"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
    with_logs: bool = typer.Option(True, "--with-logs/--no-logs", help="Try to include firmware log dump"),
    screens: bool = typer.Option(True, "--screens/--no-screens", help="Include raw display frame captures"),
    cli: bool = typer.Option(True, "--cli/--no-cli", help="Include read-only CLI diagnostics"),
):
    return _finish(run_report(_args(
        device=device,
        port=port,
        http_port=http_port,
        output=output,
        api_token=api_token,
        timeout=timeout,
        no_wait=no_wait,
        with_logs=with_logs,
        screens=screens,
        cli=cli,
    )))


@app.command("storage", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}, help="Run the embedded storage.py utility on the device")
def storage(
    ctx: typer.Context,
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
):
    return _finish(run_storage(_args(device=device, port=port, no_wait=no_wait, storage_args=list(ctx.args))))


@app.command("install", help="Install firmware from an explicit source")
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
    common = _firmware_args(source, target, update, bkp, signed, unsigned, default_bundle="update")
    return _finish(run_install(_args(
        **common,
        device=device,
        port=port,
        no_wait=no_wait,
        invoke_update=not no_install,
        via_storage=via_storage,
    )))


@app.command("fetch", help="Download and optionally unpack a firmware bundle locally")
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
    common = _firmware_args(source, target, update, bkp, signed, unsigned, default_bundle="update")
    return _finish(run_fetch(_args(**common, unpack=unpack, output=output)))


@app.command("write-recovery", help="Write a firmware bundle into the recovery partition")
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
    common = _firmware_args(source, target, update, bkp, signed, unsigned, default_bundle="bkp")
    return _finish(run_write_recovery(_args(
        **common,
        device=device,
        port=port,
        no_wait=no_wait,
        confirm_timeout=confirm_timeout,
    )))


@app.command("install-onboard", help="Install firmware already staged on the device")
def install_onboard(
    device_path: str = typer.Argument("", help="On-device path to install from, or 'recovery'"),
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
):
    return _finish(run_update_local(_args(device_path=device_path, device=device, port=port, no_wait=no_wait)))


@app.command("wait", help="Wait for the device to be reachable via ping")
def wait(
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
):
    return _finish(run_wait_for_device(_args(device=device, port=port, no_wait=False)))


@app.command("clean", help="Clean the package tmp/cache directory")
def clean():
    return _finish(run_clean(_args()))


def busybar_main(argv=None):
    logging.debug("cwd: %s", __import__("os").getcwd())
    args = list(sys.argv[1:] if argv is None else argv)
    if args in ([], ["--help"], ["-h"]):
        _print_top_level_help()
        return 0
    if args == ["--version"]:
        print(f"busybar-tools {__version__}")
        return 0

    command = typer.main.get_command(app)
    try:
        result = command.main(args=args, prog_name="busybar", standalone_mode=False)
        return 0 if result is None else result
    except click.exceptions.Exit as e:
        return e.exit_code
    except click.ClickException as e:
        e.show()
        return e.exit_code


def main():
    setup_logging()

    if sys.platform == "win32":
        from busybar_tools.bsb_term import _enable_windows_vt_mode
        _enable_windows_vt_mode()

    try:
        ret = busybar_main()
        if ret and ret != 0:
            print("Run: Exiting with error code", ret, file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        print("Run: Exited", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Run: Error: {e}", file=sys.stderr)
        sys.exit(3)
