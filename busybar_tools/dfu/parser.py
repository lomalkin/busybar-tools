import logging
import struct
import zlib
from dataclasses import dataclass


@dataclass
class DfuSeImage:
    target_name: str
    address: int
    data: bytes
    crc32_check: bool


STM32U5_FLASH_START = 0x08000000
STM32U5_FLASH_END = 0x08200000


def _read_u32le(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _dfu_crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def parse_dfuse_file(file_path, expected_target=None):
    """Parse the first DfuSe target/element from a .dfu file."""
    with open(file_path, "rb") as f:
        raw = f.read()

    if len(raw) < 293:
        raise RuntimeError(f"DFU file is too short: {file_path}")
    if raw[:5] != b"DfuSe":
        raise RuntimeError(f"Not a DfuSe file: {file_path}")

    target_name = raw[22:277].split(b"\0", 1)[0].decode(errors="replace")
    if expected_target:
        expected = str(expected_target).lower()
        if not target_name.lower().endswith(expected):
            raise RuntimeError(f"DFU target mismatch: expected {expected_target}, got '{target_name}'")

    address = _read_u32le(raw, 285)
    size = _read_u32le(raw, 289)
    end = 293 + size
    if end > len(raw):
        raise RuntimeError(f"DFU element extends past end of file: size={size}, file={len(raw)}")

    crc_ok = _dfu_crc32(raw) == 0xFFFFFFFF
    if not crc_ok:
        logging.warning("DFU file CRC/suffix check did not match the expected DfuSe convention.")

    return DfuSeImage(
        target_name=target_name,
        address=address,
        data=raw[293:end],
        crc32_check=crc_ok,
    )


def validate_recovery_image(file_path, expected_target):
    """Parse and strictly validate a recovery image before touching USB."""
    image = parse_dfuse_file(file_path, expected_target=f"f{int(expected_target)}")
    with open(file_path, "rb") as f:
        raw = f.read()
    if raw[-8:-5] != b"UFD" or raw[-5] != 16:
        raise RuntimeError("DFU file has no valid 16-byte suffix")
    product_id, vendor_id = struct.unpack_from("<HH", raw, len(raw) - 14)
    if (vendor_id, product_id) != (0x0483, 0xDF11):
        raise RuntimeError(
            f"DFU USB identity mismatch: expected 0483:df11, got {vendor_id:04x}:{product_id:04x}"
        )
    if not image.data:
        raise RuntimeError("DFU image contains an empty firmware element")
    image_end = image.address + len(image.data)
    if image.address < STM32U5_FLASH_START or image_end > STM32U5_FLASH_END:
        raise RuntimeError(
            "DFU image is outside STM32U5 internal flash: "
            f"0x{image.address:08x}..0x{image_end:08x}"
        )
    if not image.crc32_check:
        raise RuntimeError("DFU suffix CRC is invalid")
    return image
