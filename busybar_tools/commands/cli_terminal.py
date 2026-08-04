import logging
import sys

from busybar_tools.bsb_term import run_session
from busybar_tools.config import TCP_TIMEOUT_DEFAULT
from busybar_tools.device import BusybarCli, ensure_device_reachable
from busybar_tools.errors import DeviceError
from busybar_tools.options import CliOptions


def _run_cli_batch(options: CliOptions, cmds):
    """Run a list of CLI commands non-interactively over a single connection."""
    try:
        with BusybarCli(options.endpoint.address) as bsb:
            for cmd in cmds:
                logging.info(f"> {cmd}")
                for line in bsb.cmd_oneshot(cmd, timeout=options.timeout):
                    print(line)
        return 0
    except Exception as e:
        raise DeviceError(f"CLI batch failed: {e}") from e


def run_cli_terminal(options: CliOptions):
    cli_args = list(options.commands)
    if cli_args and cli_args[0] == "--":
        cli_args = cli_args[1:]
    args_cmd = " ".join(cli_args).strip()
    interactive = options.interactive

    ensure_device_reachable(options.endpoint, enabled=options.wait_before, verbose=options.verbose)

    if args_cmd:
        if interactive:
            if sys.stdin.isatty():
                logging.info("Running command, then staying in the interactive session...")
                run_session(options.endpoint.host, options.endpoint.port, tcp_timeout=TCP_TIMEOUT_DEFAULT, prelude=args_cmd)
                return 0
            logging.warning("-i requires an interactive terminal (stdin is not a TTY); running command and exiting.")
        return _run_cli_batch(options, [args_cmd])

    if not sys.stdin.isatty():
        if interactive:
            logging.warning("-i is ignored when commands are read from stdin; exiting after running them.")
        cmds = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
        if not cmds:
            return 0
        return _run_cli_batch(options, cmds)

    logging.info("Running CLI terminal...")
    print(f"Connecting to {options.endpoint.host}:{options.endpoint.port} with timeout {TCP_TIMEOUT_DEFAULT}s...")
    print("Press Ctrl+] to exit.")
    run_session(options.endpoint.host, options.endpoint.port, tcp_timeout=TCP_TIMEOUT_DEFAULT)
    return 0


__all__ = ["run_cli_terminal"]
