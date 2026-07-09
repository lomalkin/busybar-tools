import logging
import sys

from busybar_tools.config import U5_TARGET_HW
from busybar_tools.device import device_info_target, device_read_info
from busybar_tools.helpers import wait_for_device


def _recover_resolve_target(args):
    target = getattr(args, "target", "auto")
    if str(target).lower() != "auto":
        return int(target)

    try:
        logging.info(f"Reading device info from {args.device}:{args.port}...")
        info = device_read_info(args.device, args.port, retries=2, delay=1, required_keys=("u5_firmware_target",))
        target = device_info_target(info)
        logging.info(f"Detected target {target}.")
        return target
    except Exception as e:
        logging.warning(f"Could not autodetect target from device_info: {e}")
        logging.warning(f"Falling back to default target {U5_TARGET_HW}. Use --target to override.")
        return U5_TARGET_HW


def _recover_enter_dfu(args, backend):
    from busybar_tools.dfu import DFU_MANUAL_INSTRUCTIONS, enter_dfu_via_cli, wait_for_dfu_device

    if backend.find_devices():
        logging.info("DFU device is already connected.")
        return True

    if not getattr(args, "manual_dfu", False):
        try:
            logging.info("Trying to switch the device to DFU mode via CLI...")
            enter_dfu_via_cli(args.device, args.port)
            if wait_for_dfu_device(backend, timeout=getattr(args, "dfu_timeout", 30)):
                logging.info("DFU device detected.")
                return True
            logging.warning("The device did not appear in DFU mode after the CLI command.")
        except Exception as e:
            logging.warning(f"Could not switch to DFU mode automatically: {e}")

    print(DFU_MANUAL_INSTRUCTIONS)
    if sys.stdin.isatty():
        input("Press Enter when BUSY Bar is in DFU mode...")
    else:
        logging.error("Cannot prompt for manual DFU mode because stdin is not interactive.")
        return False

    if wait_for_dfu_device(backend, timeout=getattr(args, "dfu_timeout", 30)):
        logging.info("DFU device detected.")
        return True
    logging.error("DFU device was not detected.")
    return False


def run_recover(args):
    """Recover STM32U5 firmware via USB DFU."""
    from busybar_tools.dfu import RECOVERY_RESET_INSTRUCTIONS, ensure_recovery_backend, resolve_recovery_dfu

    try:
        backend = ensure_recovery_backend(
            getattr(args, "backend", "pyusb"),
            dfu_util_executable=getattr(args, "dfu_tool", None),
            auto_install_dfu_util=not getattr(args, "no_install_dfu_tool", False),
        )
    except Exception as e:
        logging.error(str(e))
        return 1

    target = _recover_resolve_target(args)
    source = getattr(args, "file", None) or args.source

    try:
        dfu_file = resolve_recovery_dfu(source, target)
        logging.info(f"Using recovery DFU file: {dfu_file}")
    except Exception as e:
        logging.error(f"Could not resolve recovery DFU firmware: {e}")
        return 1

    if not _recover_enter_dfu(args, backend):
        return 1

    try:
        backend.program_firmware(dfu_file)
    except Exception as e:
        logging.error(f"Recovery flashing failed: {e}")
        return 1

    try:
        logging.info("Sending explicit DfuSe leave command...")
        backend.leave_dfu()
        if getattr(backend, "leave_status_uncertain", False):
            logging.warning("DfuSe leave request was submitted, but the follow-up status check failed.")
            print(RECOVERY_RESET_INSTRUCTIONS)
    except Exception as e:
        logging.warning(f"Could not leave DFU mode automatically: {e}")
        if getattr(backend, "supports_reset_fallback", False):
            try:
                logging.info("Trying USB reset fallback...")
                backend.program_firmware(dfu_file, reset=True)
            except Exception as reset_error:
                logging.warning(f"USB reset fallback failed: {reset_error}")
                print(RECOVERY_RESET_INSTRUCTIONS)
        else:
            print(RECOVERY_RESET_INSTRUCTIONS)

    if getattr(args, "no_wait_after", False):
        logging.info("Skipping device reachability check after recovery (--no-wait-after).")
        print(RECOVERY_RESET_INSTRUCTIONS)
        return 0

    logging.info("Waiting for the device to come back...")
    wait_result = wait_for_device(
        args.device,
        timeout=getattr(args, "wait_timeout", 120),
        verbose=getattr(args, "verbose", True),
    )
    if not wait_result.get("success"):
        logging.warning(
            "Recovery flashing finished, but the device did not respond to ping before "
            f"the {getattr(args, 'wait_timeout', 120)}s timeout."
        )
        print(RECOVERY_RESET_INSTRUCTIONS)
        return 0
    print("Recovery DFU flashing complete.")
    return 0


__all__ = ["run_recover"]
