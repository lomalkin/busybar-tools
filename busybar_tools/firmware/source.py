import json
import logging
import os

from busybar_tools.cache import url_cache_key, workdir
from busybar_tools.config import UPDATE_DIRECTORY_URL
from busybar_tools.downloads import fetch_text
from busybar_tools.errors import FirmwareError
from busybar_tools.firmware.index import normalize_update_url
from busybar_tools.firmware.repository import download_file_info, download_matching_file, load_index
from busybar_tools.options import FirmwareSelection

CHANNEL_ALIASES = {
    "dev": "development",
    "development": "development",
    "rc": "release-candidate",
    "release-candidate": "release-candidate",
    "release": "release",
}


def _download_directory_match(source, target, file_type, cache_dir):
    if source.startswith(("http://", "https://")):
        if not source.endswith(".json"):
            raise FirmwareError(f"Source URL is not a firmware directory.json: {source}")
        directory_url = source
        channel_id = "release"
    else:
        channel_id = CHANNEL_ALIASES.get(source)
        if not channel_id:
            raise FirmwareError(f"Source '{source}' is not a known firmware channel")
        directory_url = UPDATE_DIRECTORY_URL

    data = fetch_text(directory_url, timeout=10)
    if not data:
        raise FirmwareError(f"Failed to fetch firmware directory {directory_url}")
    directory = json.loads(data)
    channel = next((item for item in directory.get("channels", []) if item.get("id") == channel_id), None)
    if not channel:
        raise FirmwareError(f"Firmware channel '{channel_id}' not found in {directory_url}")

    target_name = f"f{int(target)}"
    versions = sorted(channel.get("versions", []), key=lambda item: item.get("timestamp", 0), reverse=True)
    for version in versions:
        for file_info in version.get("files", []):
            if file_info.get("type") == file_type and str(file_info.get("target", "")).lower() == target_name:
                logging.info(
                    "Resolved %s for %s from %s channel version %s",
                    file_type, target_name, channel_id, version.get("version", "?"),
                )
                return download_file_info(file_info, cache_dir)
    raise FirmwareError(f"No {file_type} file found for {target_name} in {channel_id}")


def _download_archive(selection, source_url, file_type, cache_dir):
    if selection.source in CHANNEL_ALIASES:
        return _download_directory_match(
            selection.source, selection.target, f"{file_type}_tgz", cache_dir,
        )
    try:
        index = load_index(source_url, selection.target, cache_dir)
        return download_matching_file(f"{file_type}_tgz", cache_dir, index)
    except Exception as index_error:
        logging.warning("Could not resolve %s_tgz from update index: %s", file_type, index_error)
        return _download_directory_match(
            selection.source, selection.target, f"{file_type}_tgz", cache_dir,
        )


def resolve_source(selection: FirmwareSelection):
    if os.path.isfile(selection.source):
        path = os.path.abspath(selection.source)
        logging.info("Considering source as FILE: %s -> %s", selection.source, path)
        return path, None
    if os.path.isdir(selection.source):
        path = os.path.abspath(selection.source)
        logging.info("Considering source as DIR: %s -> %s", selection.source, path)
        return None, path

    source_url = normalize_update_url(selection.source)
    logging.info("Considering source as URL/tag/branch: %s -> %s", selection.source, source_url)
    file_type = selection.bundle_type + ("_signed" if selection.signed else "")
    if selection.save_as_recovery and selection.bundle_type != "bkp":
        logging.warning(
            "Recovery partition is normally written with a bkp bundle; proceeding with %s.",
            selection.bundle_type,
        )
    cache_dir = workdir(url_cache_key(source_url))
    archive = None
    try:
        archive = _download_archive(selection, source_url, file_type, cache_dir)
    except Exception as exc:
        logging.error("Failed to get file by type %s_tgz: %s", file_type, exc)
    if archive is None:
        try:
            archive = download_matching_file(
                f"{file_type}_tar",
                cache_dir,
                load_index(source_url, selection.target, cache_dir),
            )
        except Exception as exc:
            logging.error("Failed to get file by type %s_tar: %s", file_type, exc)
    if archive is None:
        raise FirmwareError(f"No suitable update file ({file_type}_tgz/_tar) found for {source_url}")
    return archive, None

