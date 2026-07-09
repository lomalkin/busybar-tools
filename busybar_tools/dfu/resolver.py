import json
import logging
import os

from busybar_tools.helpers import (
    busybar_update_get_index_file_name,
    busybar_update_parse_index,
    busybar_update_url_normalize,
    busybar_workdir_get,
    fetch_url,
    file_download,
    file_sha256,
    url_to_dir_name,
)


def _download_index_file(source_url, target, work_dir):
    index_name = busybar_update_get_index_file_name(target)
    index_url = f"{source_url}{index_name}"
    index_data = fetch_url(index_url, timeout=10)
    if not index_data:
        raise RuntimeError(f"Failed to fetch DFU index {index_url}")

    index_path = os.path.join(work_dir, index_name)
    with open(index_path, "w") as f:
        f.write(index_data)
    return busybar_update_parse_index(index_data, source_url)


def _download_index_match(source_url, target, work_dir):
    index_parsed = _download_index_file(source_url, target, work_dir)
    candidates = ("recovery_dfu", "recovery_dfu_dfu", "firmware_dfu", "dfu")
    for candidate in candidates:
        for file_info in index_parsed:
            if file_info.get("file_type") != candidate:
                continue
            file_path = os.path.join(work_dir, file_info["file_name"])
            if not os.path.exists(file_path):
                file_path = file_download(file_info["file_url"], file_info["file_name"], work_dir, progress=True)
            actual_hash = file_sha256(file_path)
            if actual_hash != file_info["sha256sum"]:
                logging.warning(f"DFU hash mismatch for {file_info['file_name']}; downloading again")
                file_path = file_download(file_info["file_url"], file_info["file_name"], work_dir, progress=True)
                actual_hash = file_sha256(file_path)
            if actual_hash != file_info["sha256sum"]:
                raise RuntimeError(
                    f"DFU hash check failed for {file_info['file_name']}: "
                    f"expected {file_info['sha256sum']}, got {actual_hash}"
                )
            return file_path
    raise RuntimeError(f"No recovery DFU file found in update index for target {target}")


def _download_directory_json_match(source, target, work_dir):
    if source.startswith("http://") or source.startswith("https://"):
        directory_url = source
    else:
        directory_url = "https://update.flipperzero.one/busybar-firmware/directory.json"

    data = fetch_url(directory_url, timeout=10)
    if not data:
        raise RuntimeError(f"Failed to fetch firmware directory {directory_url}")

    directory = json.loads(data)
    channel_aliases = {
        "dev": "development",
        "development": "development",
        "rc": "release-candidate",
        "release-candidate": "release-candidate",
        "release": "release",
    }
    channel_id = channel_aliases.get(source, "release")
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
            file_path = os.path.join(work_dir, name)
            if not os.path.exists(file_path):
                file_path = file_download(url, name, work_dir, progress=True)
            expected = file_info.get("sha256")
            actual = file_sha256(file_path)
            if expected and actual != expected:
                raise RuntimeError(f"DFU hash check failed for {name}: expected {expected}, got {actual}")
            return file_path

    raise RuntimeError(f"No recovery DFU file found for {target_name} in {channel_id}")


def resolve_recovery_dfu(source, target):
    if os.path.isfile(source):
        path = os.path.abspath(source)
        if not path.lower().endswith(".dfu"):
            raise RuntimeError(f"Recovery source must be a .dfu file, got: {path}")
        return path

    source_url = busybar_update_url_normalize(source)
    work_dir = busybar_workdir_get(url_to_dir_name(source_url) + "_dfu")
    try:
        return _download_index_match(source_url, target, work_dir)
    except Exception as index_error:
        logging.warning(f"Could not resolve DFU from update index: {index_error}")
        return _download_directory_json_match(source, target, work_dir)

