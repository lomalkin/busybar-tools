import logging
import os

from busybar_tools.downloads import download_file, fetch_text
from busybar_tools.errors import FirmwareError
from busybar_tools.firmware.index import index_filename, parse_index, sha256_file


def load_index(base_url, target, cache_dir):
    name = index_filename(target)
    url = f"{base_url}{name}"
    data = fetch_text(url, timeout=10)
    path = os.path.join(cache_dir, name)
    if data:
        try:
            with open(path, "w", encoding="utf-8") as output:
                output.write(data)
        except OSError as exc:
            logging.warning("Could not cache firmware index %s: %s", path, exc)
    else:
        try:
            with open(path, "r", encoding="utf-8") as source:
                data = source.read()
            logging.info("Loaded firmware index from cache %s", path)
        except OSError as exc:
            raise FirmwareError(f"Could not load update index from network or cache: {url}") from exc
    return parse_index(data, base_url)


def download_matching_file(file_type, cache_dir, index):
    logging.info("Looking for firmware file type %s...", file_type)
    file_info = next((item for item in index if item["file_type"] == file_type), None)
    if file_info is None:
        return None

    path = os.path.join(cache_dir, file_info["file_name"])
    if not os.path.exists(path):
        path = download_file(file_info["file_url"], file_info["file_name"], cache_dir, progress=True)
    actual = sha256_file(path)
    if actual != file_info["sha256sum"]:
        logging.warning("Hash mismatch for %s; downloading again", file_info["file_name"])
        path = download_file(file_info["file_url"], file_info["file_name"], cache_dir, progress=True)
        actual = sha256_file(path)
    if actual != file_info["sha256sum"]:
        raise FirmwareError(
            f"Hash check failed for {file_info['file_name']}: "
            f"expected {file_info['sha256sum']}, got {actual}"
        )
    return path


def download_file_info(file_info, cache_dir):
    url = file_info["url"]
    name = os.path.basename(url.split("?", 1)[0])
    if not name:
        raise FirmwareError(f"Could not determine file name from update URL: {url}")
    path = os.path.join(cache_dir, name)
    if not os.path.exists(path):
        path = download_file(url, name, cache_dir, progress=True)
    expected = file_info.get("sha256")
    if expected and sha256_file(path) != expected:
        logging.warning("Hash mismatch for %s; downloading again", name)
        path = download_file(url, name, cache_dir, progress=True)
        actual = sha256_file(path)
        if actual != expected:
            raise FirmwareError(f"Hash check failed for {name}: expected {expected}, got {actual}")
    return path

