import json
import logging
import os

from busybar_tools.config import UPDATE_DIRECTORY_URL
from busybar_tools.helpers import (
    busybar_update_get_index_file_name,
    busybar_update_parse_index,
    busybar_update_url_normalize,
    busybar_workdir_get,
    fetch_url,
    file_download,
    file_sha256,
    print_pretty,
    url_to_dir_name,
)

DIRECTORY_CHANNEL_ALIASES = {
    "dev": "development",
    "development": "development",
    "rc": "release-candidate",
    "release-candidate": "release-candidate",
    "release": "release",
}


class DfuIntegrityError(RuntimeError):
    """A downloaded recovery image failed its hash check.

    Must abort resolution: falling back to another (possibly unverified) source
    after an integrity failure would defeat the check.
    """


def _verified_download(url, name, work_dir, expected_sha256):
    """Download (or reuse a cached) file and verify its sha256, same as regular bundles.

    Mirrors busybar_download_file_by_filetype, except a repeated mismatch is fatal:
    a recovery image must never be flashed unverified.
    """
    file_path = os.path.join(work_dir, name)
    if not os.path.exists(file_path):
        file_path = file_download(url, name, work_dir, progress=True)
    if not file_path:
        raise RuntimeError(f"Download failed: {url}")

    actual = file_sha256(file_path)
    if actual != expected_sha256:
        logging.warning(f"File Hash check failed: {name}")
        file_path = file_download(url, name, work_dir, progress=True)
        if not file_path:
            raise RuntimeError(f"Download failed: {url}")
        actual = file_sha256(file_path)
    if actual != expected_sha256:
        raise DfuIntegrityError(f"DFU hash check failed for {name}: expected {expected_sha256}, got {actual}")
    logging.info(f"Hash check passed: {name}: {expected_sha256}")
    return file_path


def _download_index_match(source_url, target, work_dir):
    index_name = busybar_update_get_index_file_name(target)
    index_url = f"{source_url}{index_name}"
    index_data = fetch_url(index_url, timeout=10)
    if not index_data:
        raise RuntimeError(f"Failed to fetch DFU index {index_url}")
    index_parsed = busybar_update_parse_index(index_data, source_url)

    for file_info in index_parsed:
        if file_info.get("file_type") != "recovery_dfu":
            continue
        return _verified_download(
            file_info["file_url"], file_info["file_name"], work_dir, file_info["sha256sum"]
        )
    raise RuntimeError(f"No recovery DFU file found in update index for target {target}")


def _download_directory_match(source, target, work_dir):
    if source.startswith("http://") or source.startswith("https://"):
        if not source.endswith(".json"):
            raise RuntimeError(f"Source URL is not a firmware directory.json: {source}")
        directory_url = source
        channel_id = "release"
        logging.info(f"Using explicit firmware directory {directory_url} (channel '{channel_id}').")
    elif source in DIRECTORY_CHANNEL_ALIASES:
        directory_url = UPDATE_DIRECTORY_URL
        channel_id = DIRECTORY_CHANNEL_ALIASES[source]
    else:
        raise RuntimeError(
            f"Cannot resolve '{source}': not found in the update index and it is not a release "
            f"channel ({', '.join(sorted(set(DIRECTORY_CHANNEL_ALIASES)))})."
        )

    data = fetch_url(directory_url, timeout=10)
    if not data:
        raise RuntimeError(f"Failed to fetch firmware directory {directory_url}")

    directory = json.loads(data)
    channel = next((c for c in directory.get("channels", []) if c.get("id") == channel_id), None)
    if not channel:
        raise RuntimeError(f"Release channel '{channel_id}' not found in firmware directory")

    versions = sorted(channel.get("versions", []), key=lambda v: v.get("timestamp", 0), reverse=True)
    if not versions:
        raise RuntimeError(f"No versions found in release channel '{channel_id}'")

    target_name = f"f{int(target)}"
    for version in versions:
        for file_info in version.get("files", []):
            if file_info.get("type") != "recovery_dfu":
                continue
            if str(file_info.get("target", "")).lower() != target_name:
                continue
            url = file_info["url"]
            name = os.path.basename(url.split("?", 1)[0]) or f"busybar-{target_name}-recovery.dfu"
            expected = file_info.get("sha256")
            if not expected:
                raise RuntimeError(f"Firmware directory entry for {name} has no sha256; refusing unverified recovery")
            return _verified_download(url, name, work_dir, expected)

    raise RuntimeError(f"No recovery DFU file found for {target_name} in channel '{channel_id}'")


def resolve_recovery_dfu(source, target):
    """Resolve `source` (local .dfu / update-server tag / channel / URL) to a local .dfu path."""
    if os.path.isfile(source):
        path = os.path.abspath(source)
        if not path.lower().endswith(".dfu"):
            raise RuntimeError(f"Recovery source must be a .dfu file, got: {path}")
        return path

    source_url = busybar_update_url_normalize(source)
    work_dir = busybar_workdir_get(url_to_dir_name(source_url) + "_dfu")
    try:
        return _download_index_match(source_url, target, work_dir)
    except DfuIntegrityError:
        raise
    except Exception as index_error:
        logging.warning(f"Could not resolve DFU from update index: {index_error}")
        return _download_directory_match(source, target, work_dir)
