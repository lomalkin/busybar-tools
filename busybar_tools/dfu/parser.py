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


def _read_u32le(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _dfu_crc32(data):
    return zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF


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

