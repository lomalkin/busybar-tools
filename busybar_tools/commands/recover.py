import logging
import sys

from busybar_tools.config import U5_TARGET_HW
from busybar_tools.device import device_info_target, read_device_info
from busybar_tools.errors import RecoveryError
from busybar_tools.network import wait_for_device
from busybar_tools.options import RecoveryOptions


def _recover_resolve_target(options: RecoveryOptions):
    target = options.target
    if str(target).lower() != "auto":
        return int(target)

    try:
        logging.info("Reading device info from %s:%s...", options.endpoint.host, options.endpoint.port)
        info = read_device_info(options.endpoint, retries=2, delay=1, required_keys=("u5_firmware_target",))
        target = device_info_target(info)
        logging.info(f"Detected target {target}.")
        return target
    except Exception as e:
        logging.warning(f"Could not autodetect target from device_info: {e}")
        logging.warning(f"Falling back to default target {U5_TARGET_HW}. Use --target to override.")
        return U5_TARGET_HW


def _recover_enter_dfu(options: RecoveryOptions, backend):
    from busybar_tools.dfu import DFU_MANUAL_INSTRUCTIONS, enter_dfu_via_cli, wait_for_dfu_device

    if backend.find_devices():
        logging.info("DFU device is already connected.")
        return True

    if not options.manual_dfu:
        try:
            logging.info("Trying to switch the device to DFU mode via CLI...")
            enter_dfu_via_cli(options.endpoint)
            if wait_for_dfu_device(backend, timeout=options.dfu_timeout):
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

    if wait_for_dfu_device(backend, timeout=options.dfu_timeout):
        logging.info("DFU device detected.")
        return True
    logging.error("DFU device was not detected.")
    return False


def run_recover(options: RecoveryOptions):
    """Recover STM32U5 firmware via USB DFU."""
    from busybar_tools.dfu import RECOVERY_RESET_INSTRUCTIONS, ensure_recovery_backend, resolve_recovery_dfu

    try:
        backend = ensure_recovery_backend(
            options.backend,
            dfu_util_executable=options.dfu_tool,
            auto_install_dfu_util=options.install_dfu_tool,
        )
    except Exception as e:
        raise RecoveryError(str(e)) from e

    target = _recover_resolve_target(options)
    source = options.file or options.source

    try:
        dfu_file = resolve_recovery_dfu(source, target)
        logging.info(f"Using recovery DFU file: {dfu_file}")
    except Exception as e:
        raise RecoveryError(f"Could not resolve recovery DFU firmware: {e}") from e

    if not _recover_enter_dfu(options, backend):
        raise RecoveryError("DFU device was not detected")

    try:
        backend.program_firmware(dfu_file)
    except Exception as e:
        raise RecoveryError(f"Recovery flashing failed: {e}") from e

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

    if not options.wait_after:
        logging.info("Skipping device reachability check after recovery (--no-wait-after).")
        print(RECOVERY_RESET_INSTRUCTIONS)
        return 0

    logging.info("Waiting for the device to come back...")
    wait_result = wait_for_device(
        options.endpoint.host,
        timeout=options.wait_timeout,
        verbose=options.verbose,
    )
    if not wait_result.get("success"):
        logging.warning(
            "Recovery flashing finished, but the device did not respond to ping before "
            f"the {options.wait_timeout}s timeout."
        )
        print(RECOVERY_RESET_INSTRUCTIONS)
        return 0
    print("Recovery DFU flashing complete.")
    return 0


__all__ = ["run_recover"]
