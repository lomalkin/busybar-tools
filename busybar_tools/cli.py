import logging
import sys
from importlib.metadata import version

import click
import typer

from busybar_tools.console import setup_logging
from busybar_tools.errors import BusybarError
from busybar_tools.presentation.device import register as register_device_commands
from busybar_tools.presentation.firmware import register as register_firmware_commands

try:
    import typer.rich_utils
    typer.rich_utils.rich = None
except Exception:
    pass

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

COMMAND_HELP = [
    ("auto-install", "Automatic install for regular users (autodetects target & signing)"),
    ("cli", "CLI terminal session to the device"),
    ("recover", "Recover STM32U5 firmware via USB DFU"),
    ("report", "Collect a diagnostic report archive from the device"),
    ("storage", "Run the storage utility on the device"),
    ("install", "Install firmware from an explicit source"),
    ("fetch", "Download and optionally unpack a firmware bundle locally"),
    ("write-recovery", "Write a firmware bundle into the recovery partition"),
    ("install-onboard", "Install firmware already staged on the device"),
    ("factory-reset", "Factory reset the device"),
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


@app.callback()
def _main_callback(
    version_flag: bool = typer.Option(
        False, "--version", help="Show the busybar-tools version and exit.", is_eager=True,
    ),
):
    if version_flag:
        typer.echo(f"busybar-tools {__version__}")
        raise typer.Exit()


register_firmware_commands(app)
register_device_commands(app)


def _print_top_level_help():
    print("Usage: busybar [OPTIONS] COMMAND [ARGS]...")
    print("\nFirmware installer and tooling for BUSY Bar devices.\n\nOptions:")
    print("  --version              Show the busybar-tools version and exit.")
    print("  --install-completion   Install completion for the current shell.")
    print("  --show-completion      Show completion for the current shell.")
    print("  -h, --help             Show this message and exit.\n\nCommands:")
    width = max(len(name) for name, _ in COMMAND_HELP)
    for name, description in COMMAND_HELP:
        print(f"  {name:<{width}}  {description}")
    print("\n" + TOP_EPILOG.strip())


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
    except click.exceptions.Exit as exc:
        return exc.exit_code
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code


def main():
    setup_logging()
    if sys.platform == "win32":
        from busybar_tools.bsb_term import _enable_windows_vt_mode
        _enable_windows_vt_mode()
    try:
        result = busybar_main()
        if result:
            raise SystemExit(result)
    except KeyboardInterrupt:
        print("Run: Exited", file=sys.stderr)
        raise SystemExit(130) from None
    except BusybarError as exc:
        print(f"Run: Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        logging.exception("Unexpected error")
        print(f"Run: Unexpected error: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
