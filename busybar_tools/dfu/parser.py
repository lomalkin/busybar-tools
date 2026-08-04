import logging
import struct
import zlib
from dataclasses import dataclass

from busybar_tools.dfu.constants import DFU_PRODUCT_ID, DFU_VENDOR_ID

# DfuSe file layout (ST UM0391):
#   prefix:  "DfuSe" + bVersion + dwImageSize + bTargets                = 11 bytes
#   target:  "Target" + bAlternateSetting + bTargetNamed + name[255]
#            + dwTargetSize + dwNbElements                              = 274 bytes
#   element: dwElementAddress + dwElementSize + data
#   suffix:  DFU 1.1 suffix (bcdDevice, idProduct, idVendor, bcdDFU,
#            "UFD", bLength, dwCRC)                                     = 16 bytes
DFUSE_PREFIX_SIZE = 11
TARGET_PREFIX_SIZE = 274
ELEMENT_HEADER_SIZE = 8
DFU_SUFFIX_SIZE = 16

_TARGET_NAME_OFFSET = DFUSE_PREFIX_SIZE + 11
_NB_ELEMENTS_OFFSET = DFUSE_PREFIX_SIZE + TARGET_PREFIX_SIZE - 4
_ELEMENT_OFFSET = DFUSE_PREFIX_SIZE + TARGET_PREFIX_SIZE

_USB_ID_WILDCARD = 0xFFFF


@dataclass
class DfuSeImage:
    target_name: str
    address: int
    data: bytes


def _read_u32le(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _check_suffix(raw, file_path):
    """Validate the DFU 1.1 suffix: signature, USB IDs and whole-file CRC."""
    suffix = raw[-DFU_SUFFIX_SIZE:]
    if suffix[8:11] != b"UFD" or suffix[11] != DFU_SUFFIX_SIZE:
        logging.warning(f"No DFU suffix found in {file_path}; skipping USB ID and CRC checks.")
        return

    product_id, vendor_id = struct.unpack_from("<HH", suffix, 2)
    if vendor_id not in (_USB_ID_WILDCARD, DFU_VENDOR_ID) or product_id not in (_USB_ID_WILDCARD, DFU_PRODUCT_ID):
        raise RuntimeError(
            f"DFU suffix USB IDs {vendor_id:04x}:{product_id:04x} do not match the expected "
            f"STM32 DFU IDs {DFU_VENDOR_ID:04x}:{DFU_PRODUCT_ID:04x}: {file_path}"
        )

    # dfu-util stores the raw (non-inverted) CRC-32 register as dwCRC, so hashing the
    # whole file including the stored CRC must leave the register residue 0xFFFFFFFF.
    if zlib.crc32(raw) & 0xFFFFFFFF != 0xFFFFFFFF:
        raise RuntimeError(f"DFU suffix CRC check failed: {file_path}")


def parse_dfuse_file(file_path, expected_target=None):
    """Parse and validate a single-target, single-element DfuSe file."""
    with open(file_path, "rb") as f:
        raw = f.read()

    if len(raw) < _ELEMENT_OFFSET + ELEMENT_HEADER_SIZE:
        raise RuntimeError(f"DFU file is too short: {file_path}")
    if raw[:5] != b"DfuSe":
        raise RuntimeError(f"Not a DfuSe file: {file_path}")

    targets = raw[10]
    if targets != 1:
        raise RuntimeError(f"DfuSe file has {targets} targets; only single-target files are supported: {file_path}")
    nb_elements = _read_u32le(raw, _NB_ELEMENTS_OFFSET)
    if nb_elements != 1:
        raise RuntimeError(
            f"DfuSe file has {nb_elements} elements; only single-element files are supported: {file_path}"
        )

    _check_suffix(raw, file_path)

    target_name = raw[_TARGET_NAME_OFFSET:_TARGET_NAME_OFFSET + 255].split(b"\0", 1)[0].decode(errors="replace")
    if expected_target:
        expected = str(expected_target).lower()
        if not target_name.lower().endswith(expected):
            raise RuntimeError(f"DFU target mismatch: expected {expected_target}, got '{target_name}'")

    address = _read_u32le(raw, _ELEMENT_OFFSET)
    size = _read_u32le(raw, _ELEMENT_OFFSET + 4)
    end = _ELEMENT_OFFSET + ELEMENT_HEADER_SIZE + size
    if end > len(raw):
        raise RuntimeError(f"DFU element extends past end of file: size={size}, file={len(raw)}")

    return DfuSeImage(
        target_name=target_name,
        address=address,
        data=raw[_ELEMENT_OFFSET + ELEMENT_HEADER_SIZE:end],
    )
