import logging
import sys
from importlib.metadata import version

import typer

from busybar_tools.console import setup_logging
from busybar_tools.errors import BusybarError
from busybar_tools.presentation.device import register as register_device_commands
from busybar_tools.presentation.firmware import register as register_firmware_commands

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


def busybar_main(argv=None):
    logging.debug("cwd: %s", __import__("os").getcwd())
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        args = ["--help"]

    command = typer.main.get_command(app)
    try:
        command.main(args=args, prog_name="busybar", standalone_mode=True)
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


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
