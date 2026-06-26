"""Shared pytest config.

Tests under tests/hardware/ require a live, locally connected device. They are
auto-marked `hardware` and skipped unless `--run-hardware` is given.
"""
import os

import pytest

from busybar_tools.config import DEVICE_IP, DEVICE_PORT


def pytest_addoption(parser):
    parser.addoption(
        "--run-hardware", action="store_true", default=False,
        help="Run tests that require a live connected device (tests/hardware/).",
    )
    parser.addoption(
        "--run-flash", action="store_true", default=False,
        help="Also run destructive tests that reflash/reboot the device or overwrite "
             "the recovery partition. Implies --run-hardware.",
    )
    parser.addoption(
        "--device", action="store", default=os.getenv("BUSYBAR_TEST_DEVICE", DEVICE_IP),
        help="Device IP for hardware tests (env: BUSYBAR_TEST_DEVICE).",
    )
    parser.addoption(
        "--port", action="store", type=int,
        default=int(os.getenv("BUSYBAR_TEST_PORT", DEVICE_PORT)),
        help="Device TCP port for hardware tests (env: BUSYBAR_TEST_PORT).",
    )


def pytest_collection_modifyitems(config, items):
    run_flash = config.getoption("--run-flash")
    run_hw = config.getoption("--run-hardware") or run_flash  # --run-flash implies hardware
    skip_hw = pytest.mark.skip(reason="needs --run-hardware and a connected device")
    skip_flash = pytest.mark.skip(reason="destructive: needs --run-flash and a connected device")
    for item in items:
        # Auto-gate everything living under tests/hardware/.
        if os.sep + "hardware" + os.sep not in str(item.fspath):
            continue
        item.add_marker(pytest.mark.hardware)
        is_flash = "flash" in item.keywords or "flash_final" in item.keywords
        if is_flash:
            if not run_flash:
                item.add_marker(skip_flash)
        elif not run_hw:
            item.add_marker(skip_hw)

    # Run order: offline -> safe hardware -> flashing -> flash finalizer (stable sort).
    def _tier(item):
        if os.sep + "hardware" + os.sep not in str(item.fspath):
            return 0
        if "flash_final" in item.keywords:
            return 3
        if "flash" in item.keywords:
            return 2
        return 1

    items.sort(key=_tier)
