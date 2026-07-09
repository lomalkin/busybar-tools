import logging
import sys

from busybar_tools.bsb_lite import BSB_Lite
from busybar_tools.bsb_term import run_session
from busybar_tools.config import TCP_TIMEOUT_DEFAULT
from busybar_tools.device import wait_for_device_maybe


def _run_cli_batch(args, cmds):
    """Run a list of CLI commands non-interactively over a single connection."""
    timeout = getattr(args, "timeout", 5)
    try:
        with BSB_Lite((args.device, args.port)) as bsb:
            for cmd in cmds:
                logging.info(f"> {cmd}")
                for line in bsb.cmd_oneshot(cmd, timeout=timeout):
                    print(line)
        return 0
    except Exception as e:
        logging.error(f"CLI batch failed: {e}")
        return 1


def run_cli_terminal(args):
    cli_args = list(getattr(args, "cli_args", []) or [])
    if cli_args and cli_args[0] == "--":
        cli_args = cli_args[1:]
    args_cmd = " ".join(cli_args).strip()
    interactive = getattr(args, "interactive", False)

    wait_for_device_maybe(args)

    if args_cmd:
        if interactive:
            if sys.stdin.isatty():
                logging.info("Running command, then staying in the interactive session...")
                run_session(args.device, args.port, tcp_timeout=TCP_TIMEOUT_DEFAULT, prelude=args_cmd)
                return 0
            logging.warning("-i requires an interactive terminal (stdin is not a TTY); running command and exiting.")
        return _run_cli_batch(args, [args_cmd])

    if not sys.stdin.isatty():
        if interactive:
            logging.warning("-i is ignored when commands are read from stdin; exiting after running them.")
        cmds = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
        if not cmds:
            return 0
        return _run_cli_batch(args, cmds)

    logging.info("Running CLI terminal...")
    print(f"Connecting to {args.device}:{args.port} with timeout {TCP_TIMEOUT_DEFAULT}s...")
    print("Press Ctrl+] to exit.")
    run_session(args.device, args.port, tcp_timeout=TCP_TIMEOUT_DEFAULT)
    return 0


__all__ = ["run_cli_terminal"]
