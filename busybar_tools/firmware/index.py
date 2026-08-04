import hashlib
import logging
import os
import re

from busybar_tools.config import UPDATE_SERVER_BASE
from busybar_tools.errors import FirmwareError


def firmware_type_from_filename(filename):
    match = re.match(r"^busybar-(\w+)-(\w+)-(.*)\.(\w+)$", filename)
    if not match:
        raise FirmwareError(f"Unknown firmware filename: {filename}")
    return f"{match.group(2)}_{match.group(4)}"


def index_filename(target):
    return f"busybar-f{int(target)}-sha256sum.txt"


def parse_index(index_data, base_url):
    files = []
    for line_number, line in enumerate(index_data.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            checksum, filename = line.split(maxsplit=1)
        except ValueError as exc:
            raise FirmwareError(f"Invalid firmware index line {line_number}: {line!r}") from exc
        filename = os.path.basename(filename.strip())
        files.append({
            "sha256sum": checksum.strip(),
            "file_name": filename,
            "file_url": base_url + filename,
            "file_type": firmware_type_from_filename(filename),
        })
    return files


def normalize_update_url(source):
    if source.startswith(("https://", "http://")):
        url = source
    else:
        url = UPDATE_SERVER_BASE.rstrip("/") + "/" + source.lstrip("/")
    return url.rstrip("/") + "/"


def sha256_file(path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(65536), b""):
                digest.update(chunk)
    except OSError as exc:
        logging.warning("Can't calculate SHA256 for %s: %s", path, exc)
        return None
    return digest.hexdigest()

