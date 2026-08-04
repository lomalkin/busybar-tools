# PYTHONARGCOMPLETE_OK
import os
import sys
import argparse
import logging
from importlib.metadata import version

from busybar_tools import (
    run_clean,
    run_cli_terminal,
    run_update_local,
    run_wait_for_device,
    run_auto_install,
    run_install,
    run_fetch,
    run_write_recovery,
    run_recover,
    run_factory_reset,
    run_storage,
)

from busybar_tools.helpers import (
    setup_logging,
)

from busybar_tools.config import (
    DEVICE_IP,
    DEVICE_IP_REF,
    DEVICE_PORT,
    U5_TARGET_HW,
    UPDATE_DEFAULT_BRANCH,
    CONFIRM_TIMEOUT_DEFAULT,
    RECOVERY_SOURCE_DEFAULT,
    DFU_WAIT_TIMEOUT_DEFAULT,
    RECOVERY_WAIT_TIMEOUT_DEFAULT,
    FACTORY_RESET_OFFLINE_TIMEOUT_DEFAULT,
)

__version__ = "unknown"
try:
    __version__ = version("busybar-tools")
except Exception:
    __version__ = "unknown"


TOP_EPILOG = """\
examples:
  busybar auto-install          autodetect & install the latest dev firmware (recommended)
  busybar auto-install 0.10.2   install a specific tag

Most users want `busybar auto-install`. Other commands are explicit/low-level —
run `busybar <command> --help` for details.
"""

# `source` accepts (resolved in this priority order):
SOURCE_HELP = (
    "Firmware source (required). Accepted forms (priority order): "
    "explicit URL (http/https) | local bundle file | local directory | "
    "update-server tag/branch."
)


def _make_device_opts():
    """Parent parser: which device to talk to. Shared by device-facing commands."""
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("device")
    g.add_argument("-d", "--device", help=f"Device IP (or 'r'/'ref' for the reference device), default: {DEVICE_IP}", type=str, default=DEVICE_IP)
    g.add_argument("-p", "--port", help=f"Device port, default: {DEVICE_PORT}", type=int, default=DEVICE_PORT)
    return p


def _make_no_wait_opts():
    """Parent parser: opt out of the device reachability (ping) check.

    Attached to device-facing commands except `wait` (whose whole purpose is to wait).
    """
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--no-wait", dest="no_wait", action="store_true", help="Skip the device reachability (ping) check before the operation")
    return p


def _make_firmware_opts():
    """Parent parser: which firmware to take. Shared by install and fetch."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("source", help=SOURCE_HELP, type=str)

    g = p.add_argument_group("firmware selection (update server only)")
    g.add_argument("-t", "--target", help=f"Target hardware version (default: {U5_TARGET_HW}). Any integer; must exist on the update server.", type=int, default=U5_TARGET_HW)

    # Bundle type: update (default) vs bkp. Canonical build-server artifact names.
    bundle_type = g.add_mutually_exclusive_group()
    bundle_type.add_argument("--update", dest="update_bundle_type", action="store_const", const="update", help="Regular update bundle (default)")
    bundle_type.add_argument("--bkp", dest="update_bundle_type", action="store_const", const="bkp", help="Recovery (bkp) bundle instead of update")

    # Signature: signed (default) vs unsigned.
    sign = g.add_mutually_exclusive_group()
    sign.add_argument("--signed", dest="signed", action="store_true", help="Use signed firmware (default)")
    sign.add_argument("--unsigned", dest="signed", action="store_false", help="Use unsigned firmware")

    p.set_defaults(signed=True, update_bundle_type="update")
    return p


def busybar_main():
    logging.debug(f"cwd: {os.getcwd()}")

    device_opts = _make_device_opts()
    no_wait_opts = _make_no_wait_opts()
    # NOTE: firmware_opts must be a FRESH instance per command. argparse `parents=`
    # shares the same action objects, and set_defaults() mutates action.default on them —
    # so a shared firmware_opts would let write-recovery's --bkp default leak into install/fetch.

    parser = argparse.ArgumentParser(
        prog="busybar",
        description="Firmware installer and tooling for BUSY Bar devices.",
        epilog=TOP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"busybar-tools {__version__}")

    subparsers = parser.add_subparsers(
        dest="command", help="Commands to run", required=False
    )

    # auto-install -----------------------------------------------------------
    p_auto = subparsers.add_parser(
        "auto-install",
        parents=[device_opts, no_wait_opts],
        help="Automatic install for regular users (autodetects target & signing)",
        description="Autodetect the device's target and signing, fetch the matching update bundle, "
                    "install it, then report the version change. Source: update-server tag/branch or URL.",
    )

    # Transport: storage (default) vs http.
    transport_group = p_auto.add_argument_group("delivery / transport")
    transport_mx = transport_group.add_mutually_exclusive_group()
    transport_mx.add_argument("--via-storage", dest="via_storage", action="store_true", help="Deliver via storage.py protocol (default)")
    transport_mx.add_argument("--via-http", dest="via_storage", action="store_false", help="Deliver via HTTP API (direct install only)")

    p_auto.add_argument("--no-wait-after", dest="no_wait_after", action="store_true", help="Skip waiting for the device to come back online after the operation")

    p_auto.add_argument("source", help=f"Update-server tag/branch or URL (default: {UPDATE_DEFAULT_BRANCH})", type=str, default=UPDATE_DEFAULT_BRANCH, nargs="?")
    p_auto.set_defaults(func=run_auto_install, via_storage=True)

    # cli --------------------------------------------------------------------
    p_run_cli = subparsers.add_parser(
        "cli", parents=[device_opts, no_wait_opts],
        help="CLI terminal session to the device",
        description="Interactive CLI session, or run commands non-interactively:\n"
                    "  busybar cli                       interactive session (Ctrl+] to exit)\n"
                    "  busybar cli -- device_info        run one command and exit\n"
                    "  busybar cli -i -- device_info     run one command, then stay interactive\n"
                    "  echo device_info | busybar cli    run commands from stdin (one per line) and exit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_run_cli.add_argument("-i", "--interactive", dest="interactive", action="store_true", help="After running commands from arguments, stay in the interactive session (args form only)")
    p_run_cli.add_argument("--timeout", dest="timeout", metavar="SECONDS", type=int, default=5, help="Per-command response wait cap for non-interactive runs (default: 5)")
    p_run_cli.add_argument("cli_args", nargs=argparse.REMAINDER, help="Command to run, after `--` (e.g. -- sysctl debug 1)")
    p_run_cli.set_defaults(func=run_cli_terminal)

    # storage ----------------------------------------------------------------
    p_storage = subparsers.add_parser(
        "storage", parents=[device_opts, no_wait_opts], help="Run the embedded storage.py utility on the device"
    )
    p_storage.add_argument("storage_args", nargs=argparse.REMAINDER, help="Sub-command and arguments passed to storage.py (e.g. -- list /ext)")
    p_storage.set_defaults(func=run_storage)

    # install ----------------------------------------------------------------
    p_install = subparsers.add_parser(
        "install",
        parents=[_make_firmware_opts(), device_opts, no_wait_opts],
        help="Install firmware on the device",
        description="Resolve a firmware source, deliver it to the device and install it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p_install.add_argument("--no-install", dest="invoke_update", action="store_false", help="Upload the bundle to the staging dir but do not install it (--via-storage only)")

    p_install.set_defaults(func=run_install, via_storage=True)

    # Transport: storage (default) vs http.
    transport_group = p_install.add_argument_group("delivery / transport")
    transport_mx = transport_group.add_mutually_exclusive_group()
    transport_mx.add_argument("--via-storage", dest="via_storage", action="store_true", help="Deliver via storage.py protocol (default)")
    transport_mx.add_argument("--via-http", dest="via_storage", action="store_false", help="Deliver via HTTP API (direct install only)")

    # fetch ------------------------------------------------------------------
    p_fetch = subparsers.add_parser(
        "fetch",
        parents=[_make_firmware_opts()],
        help="Download (and optionally unpack) a firmware bundle locally",
        description="Fetch a firmware bundle without touching the device.",
    )
    p_fetch.add_argument("--unpack", dest="unpack", action="store_true", help="Also unpack the downloaded bundle")
    p_fetch.add_argument("-o", "--output", dest="output", type=str, default=None, help="Destination directory or file path; if omitted, the package cache is used")
    p_fetch.set_defaults(func=run_fetch)

    # write-recovery ---------------------------------------------------------
    p_write_recovery = subparsers.add_parser(
        "write-recovery",
        parents=[_make_firmware_opts(), device_opts, no_wait_opts],
        help="Write a firmware bundle into the device recovery partition (without installing)",
        description="Store a firmware bundle into the recovery partition (/bkp) WITHOUT installing it. "
                    "Defaults to --bkp. DANGER: a wrong bundle can brick the device.",
    )
    p_write_recovery.add_argument("--confirm-timeout", dest="confirm_timeout", metavar="SECONDS", type=int, default=CONFIRM_TIMEOUT_DEFAULT, help="Countdown (seconds) before overwriting the recovery partition")
    # The recovery partition expects a bkp-type bundle, so default to --bkp here.
    p_write_recovery.set_defaults(func=run_write_recovery, update_bundle_type="bkp")

    # install-onboard --------------------------------------------------------
    p_onboard = subparsers.add_parser(
        "install-onboard",
        parents=[device_opts, no_wait_opts],
        help="Install firmware already staged on the device",
        description="Invoke installation from a bundle already present on the device storage.",
    )
    p_onboard.add_argument("device_path", help="Path on the device to install from, or the literal 'recovery' for the recovery partition (default: the staged update dir)", type=str, default="", nargs="?")
    p_onboard.set_defaults(func=run_update_local)

    # recover ----------------------------------------------------------------
    p_recover = subparsers.add_parser(
        "recover",
        parents=[device_opts],
        help="Recover the U5 firmware via USB DFU",
        description="Erase and reflash the U5 internal flash over USB DFU. DANGER: destructive; "
                    "the image is validated (DfuSe target, USB IDs, CRC) and a countdown runs before flashing. "
                    "Requires the [dfu] extra (pyusb) or dfu-util.",
    )
    p_recover.add_argument("source", help=f"Update-server tag/branch/channel or URL (default: {RECOVERY_SOURCE_DEFAULT})", type=str, default=RECOVERY_SOURCE_DEFAULT, nargs="?")
    p_recover.add_argument("-t", "--target", dest="target", type=str, default="auto", help="Target hardware version, or 'auto' to autodetect via the device CLI (no fallback: pass it explicitly if the device is unreachable)")
    p_recover.add_argument("--file", dest="file", type=str, default=None, help="Use a local .dfu file instead of downloading from the update server")
    p_recover.add_argument("--backend", dest="backend", choices=["pyusb", "dfu-util", "auto"], default="pyusb", help="USB DFU backend (default: pyusb)")
    p_recover.add_argument("--dfu-tool", dest="dfu_tool", metavar="PATH", type=str, default=None, help="Path to the dfu-util executable (dfu-util/auto backend)")
    p_recover.add_argument("--install-dfu-tool", dest="install_dfu_tool", action="store_true", help="Allow installing dfu-util via the OS package manager if it is missing (dfu-util/auto backend)")
    p_recover.add_argument("--manual-dfu", dest="manual_dfu", action="store_true", help="Skip the CLI command that switches the device to DFU mode; prompt for manual entry instead")
    p_recover.add_argument("--dfu-timeout", dest="dfu_timeout", metavar="SECONDS", type=int, default=DFU_WAIT_TIMEOUT_DEFAULT, help=f"How long to wait for a DFU USB device (default: {DFU_WAIT_TIMEOUT_DEFAULT})")
    p_recover.add_argument("--wait-timeout", dest="wait_timeout", metavar="SECONDS", type=int, default=RECOVERY_WAIT_TIMEOUT_DEFAULT, help=f"How long to wait for the device to come back after flashing (default: {RECOVERY_WAIT_TIMEOUT_DEFAULT})")
    p_recover.add_argument("--no-wait-after", dest="no_wait_after", action="store_true", help="Skip waiting for the device to come back online after flashing")
    p_recover.add_argument("--confirm-timeout", dest="confirm_timeout", metavar="SECONDS", type=int, default=CONFIRM_TIMEOUT_DEFAULT, help="Countdown (seconds) before erasing and flashing")
    p_recover.set_defaults(func=run_recover)

    # factory-reset ----------------------------------------------------------
    p_factory_reset = subparsers.add_parser(
        "factory-reset",
        parents=[device_opts, no_wait_opts],
        help="Factory reset the device",
        description="Wipe the device to factory state via the CLI (sysctl debug 1, factory_reset, confirm). "
                    "DANGER: destructive; a countdown runs before the reset is invoked.",
    )
    p_factory_reset.add_argument("-s", "--shipping-mode", dest="shipping_mode", action="store_true", help="Enter shipping mode after the reset")
    p_factory_reset.add_argument("--offline-timeout", dest="offline_timeout", metavar="SECONDS", type=int, default=FACTORY_RESET_OFFLINE_TIMEOUT_DEFAULT, help=f"How long to wait for the device to drop offline (default: {FACTORY_RESET_OFFLINE_TIMEOUT_DEFAULT})")
    p_factory_reset.add_argument("--no-wait-after", dest="no_wait_after", action="store_true", help="Skip waiting for the device to come back online after the reset")
    p_factory_reset.add_argument("--confirm-timeout", dest="confirm_timeout", metavar="SECONDS", type=int, default=CONFIRM_TIMEOUT_DEFAULT, help="Countdown (seconds) before invoking the reset")
    p_factory_reset.set_defaults(func=run_factory_reset)

    # wait -------------------------------------------------------------------
    p_run_wait = subparsers.add_parser(
        "wait", parents=[device_opts], help="Wait for the device to be reachable via ping, nothing else"
    )
    p_run_wait.set_defaults(func=run_wait_for_device)

    # clean ------------------------------------------------------------------
    p_clean = subparsers.add_parser(
        "clean", help="Clean the package's tmp/cache directory"
    )
    p_clean.set_defaults(func=run_clean)


    try:  # ponytail: optional — completion works only if argcomplete is installed
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()

    if hasattr(args, "device") and args.device.lower() in ["r", "ref"]:
        args.device = DEVICE_IP_REF

    # --via-http is a direct-install transport: it cannot stage without installing.
    if args.command == "install" and not args.via_storage and not args.invoke_update:
        p_install.error("--no-install requires --via-storage (not available with --via-http)")

    args.verbose = True

    if args.command is not None:
        return args.func(args)
    else:
        parser.print_help()


def main():
    setup_logging()

    if sys.platform == "win32":
        from busybar_tools.bsb_term import _enable_windows_vt_mode
        _enable_windows_vt_mode()

    try:
        ret = busybar_main()
        # print("RET: ", ret)
        if ret and ret != 0:
            print("Run: Exiting with error code", ret, file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        print("Run: Exited", file=sys.stderr)
        sys.exit(2)
    # except subprocess.CalledProcessError as e:
    #     sys.exit(e.returncode)
    except Exception as e:
        print(f"Run: Error: {e}", file=sys.stderr)
        sys.exit(3)


# if __name__ == "__main__":
#     main()
