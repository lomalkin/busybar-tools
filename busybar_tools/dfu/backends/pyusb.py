import logging
import struct
import time

from busybar_tools.dfu.constants import DFU_PRODUCT_ID, DFU_VENDOR_ID
from busybar_tools.dfu.device import DfuDevice
from busybar_tools.dfu.parser import parse_dfuse_file


class PyUsbDfuSeBackend:
    """Minimal STM32 DfuSe backend using PyUSB."""

    DFU_INTERFACE = 0
    TRANSFER_SIZE = 1024
    FLASH_PAGE_SIZE = 8192

    REQ_DNLOAD = 1
    REQ_GETSTATUS = 3
    REQ_CLRSTATUS = 4
    REQ_ABORT = 6

    STATE_DFU_IDLE = 2
    STATE_DFU_DNBUSY = 4
    STATE_DFU_DNLOAD_IDLE = 5
    STATE_DFU_ERROR = 10
    def __init__(self):
        self.usb_core = None
        self.usb_util = None
        self.usb_backend = None
        self.device = None
        self.leave_status_uncertain = False
        self.selected_device = None

    def _import_usb(self):
        if self.usb_core is not None:
            return
        try:
            import usb.backend.libusb1
            import usb.core
            import usb.util
        except ImportError as e:
            raise RuntimeError(
                "PyUSB backend requires pyusb. Install busybar-tools with pyusb support "
                "or use `--backend dfu-util`."
            ) from e
        try:
            import libusb_package

            self.usb_backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
        except Exception as e:
            logging.debug(f"Bundled libusb backend is not available: {e}")
            self.usb_backend = None
        self.usb_core = usb.core
        self.usb_util = usb.util

    def is_available(self):
        try:
            self._import_usb()
            self.usb_core.find(find_all=False, backend=self.usb_backend)
            return True
        except Exception as e:
            logging.debug(f"PyUSB backend is not available: {e}")
            return False

    @staticmethod
    def _read_descriptor(dev, name):
        try:
            return getattr(dev, name, None)
        except Exception:
            return None

    def list_devices(self):
        self._import_usb()
        try:
            devices = self.usb_core.find(
                find_all=True,
                idVendor=DFU_VENDOR_ID,
                idProduct=DFU_PRODUCT_ID,
                backend=self.usb_backend,
            )
        except Exception as e:
            raise RuntimeError(f"Could not access USB DFU devices through PyUSB: {e}") from e

        result = []
        for dev in devices or ():
            bus = getattr(dev, "bus", None)
            address = getattr(dev, "address", None)
            serial = self._read_descriptor(dev, "serial_number")
            key = f"serial:{serial}" if serial else f"bus:{bus}:address:{address}"
            result.append(DfuDevice(
                key=key,
                vendor_id=DFU_VENDOR_ID,
                product_id=DFU_PRODUCT_ID,
                bus=bus,
                address=address,
                serial=serial,
                manufacturer=self._read_descriptor(dev, "manufacturer"),
                product=self._read_descriptor(dev, "product"),
            ))
        return result

    def select_device(self, device):
        self.selected_device = device

    def _matches_selected(self, dev):
        if self.selected_device is None:
            return True
        if self.selected_device.serial:
            return self._read_descriptor(dev, "serial_number") == self.selected_device.serial
        return (
            getattr(dev, "bus", None) == self.selected_device.bus
            and getattr(dev, "address", None) == self.selected_device.address
        )

    def _open(self):
        self._import_usb()
        try:
            devices = self.usb_core.find(
                find_all=True,
                idVendor=DFU_VENDOR_ID,
                idProduct=DFU_PRODUCT_ID,
                backend=self.usb_backend,
            )
        except Exception as e:
            raise RuntimeError(f"Could not access USB DFU devices through PyUSB: {e}") from e
        matches = [dev for dev in (devices or ()) if self._matches_selected(dev)]
        if not matches:
            raise RuntimeError("No STM32 DFU USB device found (0483:df11)")
        if len(matches) > 1:
            raise RuntimeError("Multiple STM32 DFU USB devices found; disconnect unrelated devices")
        dev = matches[0]

        try:
            dev.set_configuration()
        except Exception:
            pass

        try:
            if hasattr(dev, "is_kernel_driver_active") and dev.is_kernel_driver_active(self.DFU_INTERFACE):
                dev.detach_kernel_driver(self.DFU_INTERFACE)
        except Exception:
            pass

        self.usb_util.claim_interface(dev, self.DFU_INTERFACE)
        try:
            dev.set_interface_altsetting(interface=self.DFU_INTERFACE, alternate_setting=0)
        except Exception:
            pass

        self.device = dev
        return dev

    def _close(self):
        if self.device is None or self.usb_util is None:
            return
        try:
            self.usb_util.release_interface(self.device, self.DFU_INTERFACE)
        except Exception:
            pass
        try:
            self.usb_util.dispose_resources(self.device)
        except Exception:
            pass
        self.device = None

    def _dnload(self, block, payload=b"", timeout=5000):
        self.device.ctrl_transfer(0x21, self.REQ_DNLOAD, block, self.DFU_INTERFACE, payload, timeout=timeout)

    def _get_status(self):
        data = self.device.ctrl_transfer(0xA1, self.REQ_GETSTATUS, 0, self.DFU_INTERFACE, 6, timeout=5000)
        status = int(data[0])
        poll_timeout = int(data[1]) | (int(data[2]) << 8) | (int(data[3]) << 16)
        state = int(data[4])
        return status, poll_timeout, state

    def _clear_status(self):
        self.device.ctrl_transfer(0x21, self.REQ_CLRSTATUS, 0, self.DFU_INTERFACE, b"", timeout=5000)

    def _abort(self):
        self.device.ctrl_transfer(0x21, self.REQ_ABORT, 0, self.DFU_INTERFACE, b"", timeout=5000)

    @staticmethod
    def _check_deadline(deadline):
        if deadline is not None and time.monotonic() >= deadline:
            raise RuntimeError("DFU operation timed out")

    def _poll_until_idle(self, deadline=None):
        while True:
            self._check_deadline(deadline)
            status, poll_timeout, state = self._get_status()
            if state == self.STATE_DFU_ERROR:
                self._clear_status()
                raise RuntimeError(f"DFU error status {status}")
            if state in (self.STATE_DFU_IDLE, self.STATE_DFU_DNLOAD_IDLE):
                return
            time.sleep(max(poll_timeout, 1) / 1000.0)

    def _command(self, payload, deadline=None):
        self._dnload(0, payload)
        self._poll_until_idle(deadline)

    def _set_address(self, address, deadline=None):
        self._command(bytes([0x21]) + struct.pack("<I", int(address)), deadline)

    def _erase_page(self, address, deadline=None):
        self._command(bytes([0x41]) + struct.pack("<I", int(address)), deadline)

    def _erase_range(self, start, size, deadline=None):
        first = start - (start % self.FLASH_PAGE_SIZE)
        last = start + size
        total = max(1, ((last - first) + self.FLASH_PAGE_SIZE - 1) // self.FLASH_PAGE_SIZE)
        for index, address in enumerate(range(first, last, self.FLASH_PAGE_SIZE), start=1):
            print(f"\rErase: page {index}/{total} @ 0x{address:08x}", end="", flush=True)
            self._check_deadline(deadline)
            self._erase_page(address, deadline)
        print()

    def program_firmware(self, fw_file, timeout=180):
        image = parse_dfuse_file(fw_file)
        logging.info(
            f"Flashing DfuSe image target='{image.target_name}', "
            f"address=0x{image.address:08x}, size={len(image.data)}"
        )

        deadline = time.monotonic() + timeout if timeout and timeout > 0 else None
        self._open()
        try:
            try:
                status, _, state = self._get_status()
                if state == self.STATE_DFU_ERROR:
                    logging.warning(f"Clearing stale DFU error status {status}")
                    self._clear_status()
                elif state not in (self.STATE_DFU_IDLE, self.STATE_DFU_DNLOAD_IDLE):
                    self._abort()
            except Exception as e:
                logging.debug(f"Initial DFU status cleanup skipped: {e}")

            self._erase_range(image.address, len(image.data), deadline)
            self._set_address(image.address, deadline)

            chunks = [image.data[i:i + self.TRANSFER_SIZE] for i in range(0, len(image.data), self.TRANSFER_SIZE)]
            for index, chunk in enumerate(chunks, start=0):
                print(f"\rWrite: chunk {index + 1}/{len(chunks)}", end="", flush=True)
                self._check_deadline(deadline)
                self._dnload(index + 2, chunk)
                self._poll_until_idle(deadline)
            print()
        finally:
            self._close()

    def leave_dfu(self, address=0x08000000, timeout=15):
        self.leave_status_uncertain = False
        deadline = time.monotonic() + timeout if timeout and timeout > 0 else None
        self._open()
        try:
            self._set_address(int(address), deadline)
            try:
                self._dnload(0, b"")
                self._poll_until_idle(deadline)
            except Exception as e:
                self.leave_status_uncertain = True
                logging.info(f"DFU leave submitted; ignoring follow-up status failure: {e}")
        finally:
            self._close()
