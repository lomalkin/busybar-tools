import json
import logging
import os
import shutil

from busybar_tools.config import UPDATE_DIRECTORY_URL
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


UNPACKED_DIR_NAME = "unpacked"
CHANNEL_ALIASES = {
    "dev": "development",
    "development": "development",
    "rc": "release-candidate",
    "release-candidate": "release-candidate",
    "release": "release",
}


def busybar_get_index_by_url(base_url, target, work_dir):
    index_name = busybar_update_get_index_file_name(target)
    index_url = f"{base_url}{index_name}"

    try:
        index_data = fetch_url(index_url, timeout=10)
        if not index_data:
            raise RuntimeError(f"Failed to fetch index {index_url}")
        logging.info(f"Fetched index content from {index_url}, length: {len(index_data)} bytes")
    except Exception as e:
        index_data = None
        logging.warning(f"{e}")
        logging.info("Trying to use cached index...")

    index_path = os.path.join(work_dir, index_name)
    if index_data:
        try:
            with open(index_path, "w") as f:
                f.write(index_data)
            logging.info(f"Index content saved to {index_path}")
        except Exception as e:
            logging.error(f"Error saving index content: {e}")
    else:
        try:
            with open(index_path, "r") as f:
                index_data = f.read()
            logging.info(f"Loaded index content from cache {index_path}")
        except Exception as e:
            logging.error(f"Error loading index content from cache: {e}")
            raise RuntimeError(f"Could not load update index from network or cache: {index_url}") from e

    return busybar_update_parse_index(index_data, base_url)


def busybar_download_file_by_filetype(source_url, file_type, work_dir, index_parsed):
    logging.info(f"Trying for file_type {file_type}...")

    file_path = None
    for file in index_parsed:
        if file["file_type"] != file_type:
            continue

        file_path = os.path.join(work_dir, file["file_name"])
        if not os.path.exists(file_path):
            file_path = file_download(file["file_url"], file["file_name"], work_dir, progress=True)

        file_hash = file_sha256(file_path)
        if file_hash != file["sha256sum"]:
            logging.warning(f"File Hash check failed: {file['file_name']}")
            file_path = file_download(file["file_url"], file["file_name"], work_dir, progress=True)
            file_hash = file_sha256(file_path)

        if file_hash == file["sha256sum"]:
            logging.info(f"Hash check passed: {file['file_name']}: {file['sha256sum']}")
        else:
            logging.error(f"File Hash check failed ONCE AGAIN: {file['file_name']}: {file['sha256sum']}")
        break

    if file_path is None:
        logging.warning(f"Failed to find file of type {file_type} in index!")
    return file_path


def _download_file_from_info(file_info, work_dir):
    url = file_info["url"]
    name = os.path.basename(url.split("?", 1)[0])
    if not name:
        raise RuntimeError(f"Could not determine file name from update URL: {url}")

    file_path = os.path.join(work_dir, name)
    if not os.path.exists(file_path):
        file_path = file_download(url, name, work_dir, progress=True)

    expected_hash = file_info.get("sha256")
    if expected_hash:
        actual_hash = file_sha256(file_path)
        if actual_hash != expected_hash:
            logging.warning(f"Hash mismatch for {name}; downloading again")
            file_path = file_download(url, name, work_dir, progress=True)
            actual_hash = file_sha256(file_path)
        if actual_hash != expected_hash:
            raise RuntimeError(f"Hash check failed for {name}: expected {expected_hash}, got {actual_hash}")
    return file_path


def _download_directory_json_match(source, target, file_type, work_dir):
    if source.startswith("http://") or source.startswith("https://"):
        if not source.endswith(".json"):
            raise RuntimeError(f"Source URL is not a firmware directory.json: {source}")
        directory_url = source
        channel_id = "release"
    else:
        channel_id = CHANNEL_ALIASES.get(source)
        if not channel_id:
            raise RuntimeError(f"Source '{source}' is not a known firmware channel")
        directory_url = UPDATE_DIRECTORY_URL

    data = fetch_url(directory_url, timeout=10)
    if not data:
        raise RuntimeError(f"Failed to fetch firmware directory {directory_url}")

    directory = json.loads(data)
    channel = next((c for c in directory.get("channels", []) if c.get("id") == channel_id), None)
    if not channel:
        raise RuntimeError(f"Firmware channel '{channel_id}' not found in {directory_url}")

    versions = sorted(channel.get("versions", []), key=lambda v: v.get("timestamp", 0), reverse=True)
    target_name = f"f{int(target)}"
    for version in versions:
        for file_info in version.get("files", []):
            if file_info.get("type") != file_type:
                continue
            if str(file_info.get("target", "")).lower() != target_name:
                continue
            logging.info(
                f"Resolved {file_type} for {target_name} from {channel_id} "
                f"channel version {version.get('version', '?')}"
            )
            return _download_file_from_info(file_info, work_dir)

    raise RuntimeError(f"No {file_type} file found for {target_name} in {channel_id}")


def _download_source_file(source, source_url, target, file_type, work_dir):
    if source in CHANNEL_ALIASES:
        return _download_directory_json_match(source, target, f"{file_type}_tgz", work_dir)

    try:
        index_parsed = busybar_get_index_by_url(source_url, target, work_dir)
        return busybar_download_file_by_filetype(source_url, f"{file_type}_tgz", work_dir, index_parsed)
    except Exception as index_error:
        logging.warning(f"Could not resolve {file_type}_tgz from update index: {index_error}")
        return _download_directory_json_match(source, target, f"{file_type}_tgz", work_dir)


def resolve_source(args):
    """Determine the firmware source and download it if needed."""
    if os.path.isfile(args.source):
        source_file = os.path.abspath(args.source)
        logging.info(f"Considering source as FILE: {args.source} -> {source_file}")
        return source_file, None

    if os.path.isdir(args.source):
        source_dir = os.path.abspath(args.source)
        logging.info(f"Considering source as DIR: {args.source} -> {source_dir}")
        return None, source_dir

    args.source_url = busybar_update_url_normalize(args.source)
    logging.info(f"Considering source as URL/tag/branch: {args.source} -> {args.source_url}")

    file_type = f"{args.update_bundle_type}"
    if args.signed:
        file_type += "_signed"

    if getattr(args, "save_as_recovery", False) and args.update_bundle_type != "bkp":
        logging.warning(
            "--save-as-recovery is normally used with --bkp (the bundle type designed for the "
            f"recovery partition); proceeding with '{args.update_bundle_type}' bundle anyway."
        )

    work_dir = busybar_workdir_get(url_to_dir_name(args.source_url))

    source_file = None
    try:
        source_file = _download_source_file(args.source, args.source_url, args.target, file_type, work_dir)
    except Exception as e:
        logging.error(f"Failed to get file by type {file_type}_tgz: {e}")

    if source_file is None:
        try:
            index_parsed = busybar_get_index_by_url(args.source_url, args.target, work_dir)
            source_file = busybar_download_file_by_filetype(args.source_url, f"{file_type}_tar", work_dir, index_parsed)
        except Exception as e:
            logging.error(f"Failed to get file by type {file_type}_tar: {e}")

    if source_file is None:
        raise RuntimeError(f"No suitable update file ({file_type}_tgz/_tar) found in index for {args.source_url}")

    return source_file, None


def bundle_unpack(source_file, unpack_dir):
    logging.info(f"Unpacking update bundle {source_file} to {unpack_dir}...")
    try:
        shutil.unpack_archive(source_file, unpack_dir)
        logging.info(f"Unpacked: {os.listdir(unpack_dir)}")
        return 0
    except Exception as e:
        logging.error(f"Failed to unpack bundle: {e}")
        return 1


def unpack_bundle(source_file):
    """Unpack a bundle archive into a clean work dir; return the unpacked dir path."""
    work_dir = busybar_workdir_get("local_file")
    unpacked_bundle_dir = os.path.join(work_dir, UNPACKED_DIR_NAME)
    shutil.rmtree(unpacked_bundle_dir, ignore_errors=True)
    assert bundle_unpack(source_file, unpacked_bundle_dir) == 0
    return unpacked_bundle_dir


def _place_result(src_path, output):
    """Copy a fetched file/dir to `output`; return the final path."""
    if not output:
        return src_path

    wants_dir = output.endswith(("/", os.sep))
    output = os.path.abspath(os.path.expanduser(output))

    if os.path.isdir(src_path):
        os.makedirs(output, exist_ok=True)
        shutil.copytree(src_path, output, dirs_exist_ok=True)
        return output

    if wants_dir or os.path.isdir(output):
        os.makedirs(output, exist_ok=True)
        dst = os.path.join(output, os.path.basename(src_path))
    else:
        parent = os.path.dirname(output)
        if parent:
            os.makedirs(parent, exist_ok=True)
        dst = output
    shutil.copy2(src_path, dst)
    return dst
