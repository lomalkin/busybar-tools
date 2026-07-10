from __future__ import annotations

import base64
import struct
import zlib
from typing import Any, Dict
from zipfile import ZipFile

from busybar_tools.api import BusybarApiClient
from busybar_tools.report.models import ReportManifest
from busybar_tools.report.util import write_json


SCREEN_SPECS = {
    0: {"name": "front", "width": 72, "height": 16, "format": "rgb888"},
    1: {"name": "back", "width": 160, "height": 80, "format": "l4_nibble_packed"},
}


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def _scale_rgb_rows(rgb: bytes, width: int, height: int, scale: int) -> bytes:
    rows = []
    row_bytes = width * 3
    for y in range(height):
        src = rgb[y * row_bytes:(y + 1) * row_bytes]
        scaled = bytearray()
        for i in range(0, len(src), 3):
            scaled.extend(src[i:i + 3] * scale)
        row = b"\x00" + bytes(scaled)
        rows.extend([row] * scale)
    return b"".join(rows)


def _png_rgb(rgb: bytes, width: int, height: int, scale: int = 4) -> bytes:
    width_scaled = width * scale
    height_scaled = height * scale
    raw = _scale_rgb_rows(rgb, width, height, scale)
    return b"".join([
        b"\x89PNG\r\n\x1a\n",
        _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width_scaled, height_scaled, 8, 2, 0, 0, 0)),
        _png_chunk(b"IDAT", zlib.compress(raw)),
        _png_chunk(b"IEND", b""),
    ])


def screen_png(raw: bytes, display: int, scale: int = 4) -> bytes:
    spec = SCREEN_SPECS[display]
    width = int(spec["width"])
    height = int(spec["height"])
    if display == 0:
        expected = width * height * 3
        if len(raw) != expected:
            raise ValueError(f"front display raw size is {len(raw)}, expected {expected}")
        return _png_rgb(raw, width, height, scale=scale)

    expected = width * height // 2
    if len(raw) != expected:
        raise ValueError(f"back display raw size is {len(raw)}, expected {expected}")
    rgb = bytearray(width * height * 3)
    out_idx = 0
    for byte in raw:
        for value in (byte & 0x0F, (byte >> 4) & 0x0F):
            shade = value * 17
            rgb[out_idx:out_idx + 3] = bytes((shade, shade, shade))
            out_idx += 3
    return _png_rgb(bytes(rgb), width, height, scale=scale)


def collect_screens(
    zipf: ZipFile,
    api: BusybarApiClient,
    manifest: ReportManifest,
    collected: Dict[str, Any],
) -> None:
    screen_meta = {}
    for display, spec in SCREEN_SPECS.items():
        name = f"screen:{spec['name']}"
        try:
            encoded = api.get_bytes("/api/screen", params={"display": display})
            raw = base64.b64decode(encoded, validate=False)
            archive_path = f"screens/{spec['name']}.raw"
            zipf.writestr(archive_path, raw)
            png_path = f"screens/{spec['name']}.png"
            try:
                zipf.writestr(png_path, screen_png(raw, display))
            except Exception as exc:
                png_path = None
                manifest.failed(f"{name}:png", exc)
            screen_meta[spec["name"]] = {
                **spec,
                "display": display,
                "bytes": len(raw),
                "path": archive_path,
                "png_path": png_path,
            }
            manifest.ok(name, archive_path)
        except Exception as exc:
            manifest.failed(name, exc)
    if screen_meta:
        collected["screens/meta.json"] = screen_meta
        write_json(zipf, "screens/meta.json", screen_meta)
