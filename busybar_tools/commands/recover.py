import logging
import os
import re
import sys

from busybar_tools.device import device_info_target, read_device_info
from busybar_tools.errors import RecoveryError
from busybar_tools.network import wait_for_device
from busybar_tools.options import RecoveryOptions


def _target_from_local_dfu(options: RecoveryOptions):
    from busybar_tools.dfu import parse_dfuse_file

    source = options.file or options.source
    if not os.path.isfile(source) or not source.lower().endswith(".dfu"):
        return None
    image = parse_dfuse_file(source)
    match = re.search(r"(?:^|[^a-z0-9])f(\d+)(?:$|[^0-9])", image.target_name, re.IGNORECASE)
    if match is None:
        raise RecoveryError(
            f"Could not determine the hardware target from DfuSe target name {image.target_name!r}"
        )
    target = int(match.group(1))
    logging.info("Detected target %s from local DFU image '%s'.", target, image.target_name)
    return target


def _recover_resolve_target(options: RecoveryOptions, connected_dfu_device=None):
    target = options.target
    if str(target).lower() != "auto":
        try:
            target = int(target)
        except (TypeError, ValueError) as exc:
            raise RecoveryError(f"Invalid hardware target: {target!r}") from exc
        if target <= 0:
            raise RecoveryError("Hardware target must be a positive integer")
        return target

    if connected_dfu_device is not None:
        target = _target_from_local_dfu(options)
        if target is not None:
            return target
        raise RecoveryError(
            "The device is already in DFU mode, so its hardware target cannot be read over IP. "
            "Pass an explicit target, for example `--target 22`, or use a local `.dfu` image."
        )

    try:
        logging.info("Reading device info from %s:%s...", options.endpoint.host, options.endpoint.port)
        info = read_device_info(options.endpoint, retries=2, delay=1, required_keys=("u5_firmware_target",))
        target = device_info_target(info)
        logging.info(f"Detected target {target}.")
        return target
    except Exception as e:
        raise RecoveryError(
            "Could not autodetect the hardware target while the device CLI is unavailable. "
            "Put the device back in runtime mode or pass an explicit target, for example `--target 22`. "
            f"Details: {e}"
        ) from e


def _single_dfu_device(devices):
    if not devices:
        return None
    if len(devices) > 1:
        labels = ", ".join(device.label for device in devices)
        raise RecoveryError(
            "Multiple STM32 DFU devices were detected. Disconnect unrelated devices and retry. "
            f"Detected: {labels}"
        )
    return devices[0]


def _recover_enter_dfu(options: RecoveryOptions, backend, connected_device):
    from busybar_tools.dfu import DFU_MANUAL_INSTRUCTIONS, enter_dfu_via_cli, wait_for_dfu_devices

    if connected_device is not None:
        return connected_device

    if not options.manual_dfu:
        try:
            logging.info("Trying to switch the device to DFU mode via CLI...")
            enter_dfu_via_cli(options.endpoint)
            device = _single_dfu_device(wait_for_dfu_devices(backend, timeout=options.dfu_timeout))
            if device is not None:
                logging.info("DFU device detected: %s", device.label)
                return device
            logging.warning("The device did not appear in DFU mode after the CLI command.")
        except RecoveryError:
            raise
        except Exception as e:
            logging.warning(f"Could not switch to DFU mode automatically: {e}")

    print(DFU_MANUAL_INSTRUCTIONS)
    if sys.stdin.isatty():
        input("Press Enter when BUSY Bar is in DFU mode...")
    else:
        logging.error("Cannot prompt for manual DFU mode because stdin is not interactive.")
        return None

    device = _single_dfu_device(wait_for_dfu_devices(backend, timeout=options.dfu_timeout))
    if device is not None:
        logging.info("DFU device detected: %s", device.label)
        return device
    logging.error("DFU device was not detected.")
    return None


def _confirm_recovery(options, target, dfu_file, image, device):
    image_end = image.address + len(image.data)
    print("\nRecovery flash summary:")
    print(f"  USB device: {device.label}")
    print(f"  Hardware target: f{target}")
    print(f"  Image: {os.path.abspath(dfu_file)}")
    print(f"  DfuSe target: {image.target_name}")
    print(f"  Flash range: 0x{image.address:08x}..0x{image_end:08x} ({len(image.data)} bytes)")
    if options.assume_yes:
        logging.warning("Skipping recovery confirmation because --yes was specified.")
        return
    if not sys.stdin.isatty():
        raise RecoveryError("Recovery confirmation requires an interactive terminal; pass --yes for automation")
    expected = f"f{target}"
    entered = input(f"Type '{expected}' to erase and flash this USB device: ").strip().lower()
    if entered != expected:
        raise RecoveryError("Recovery cancelled; confirmation did not match")


def run_recover(options: RecoveryOptions):
    """Recover STM32U5 firmware via USB DFU."""
    from busybar_tools.dfu import (
        RECOVERY_RESET_INSTRUCTIONS,
        ensure_recovery_backend,
        resolve_recovery_dfu,
        validate_recovery_image,
    )

    for name, value in (
        ("DFU detection timeout", options.dfu_timeout),
        ("flash timeout", options.flash_timeout),
        ("post-flash wait timeout", options.wait_timeout),
    ):
        if value <= 0:
            raise RecoveryError(f"{name} must be positive")

    try:
        backend = ensure_recovery_backend(
            options.backend,
            dfu_util_executable=options.dfu_tool,
            auto_install_dfu_util=options.install_dfu_tool,
        )
    except Exception as e:
        raise RecoveryError(str(e)) from e

    try:
        connected_device = _single_dfu_device(backend.list_devices())
    except RecoveryError:
        raise
    except Exception as e:
        raise RecoveryError(f"Could not inspect USB DFU devices: {e}") from e
    if connected_device is not None:
        logging.info("DFU device is already connected: %s", connected_device.label)

    target = _recover_resolve_target(options, connected_device)
    source = options.file or options.source

    try:
        dfu_file = resolve_recovery_dfu(source, target)
        logging.info(f"Using recovery DFU file: {dfu_file}")
        image = validate_recovery_image(dfu_file, target)
    except Exception as e:
        raise RecoveryError(f"Could not resolve recovery DFU firmware: {e}") from e

    device = _recover_enter_dfu(options, backend, connected_device)
    if device is None:
        raise RecoveryError("DFU device was not detected")
    backend.select_device(device)
    _confirm_recovery(options, target, dfu_file, image, device)

    try:
        backend.program_firmware(dfu_file, timeout=options.flash_timeout)
    except Exception as e:
        raise RecoveryError(f"Recovery flashing failed: {e}") from e

    try:
        logging.info("Sending explicit DfuSe leave command...")
        backend.leave_dfu(address=image.address)
        if getattr(backend, "leave_status_uncertain", False):
            logging.warning("DfuSe leave request was submitted, but the follow-up status check failed.")
            print(RECOVERY_RESET_INSTRUCTIONS)
    except Exception as e:
        logging.warning(f"Could not leave DFU mode automatically: {e}")
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
