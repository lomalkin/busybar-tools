import logging
import os
import shutil

from busybar_tools.cache import workdir
from busybar_tools.errors import FirmwareError

UNPACKED_DIR_NAME = "unpacked"


def unpack_bundle(source_file):
    destination = os.path.join(workdir("local_file"), UNPACKED_DIR_NAME)
    shutil.rmtree(destination, ignore_errors=True)
    logging.info("Unpacking update bundle %s to %s...", source_file, destination)
    try:
        shutil.unpack_archive(source_file, destination)
    except (OSError, shutil.ReadError) as exc:
        raise FirmwareError(f"Failed to unpack firmware bundle {source_file}: {exc}") from exc
    logging.info("Unpacked: %s", os.listdir(destination))
    return destination


def place_result(source_path, output):
    if not output:
        return source_path
    wants_directory = output.endswith(("/", os.sep))
    output = os.path.abspath(os.path.expanduser(output))
    if os.path.isdir(source_path):
        os.makedirs(output, exist_ok=True)
        shutil.copytree(source_path, output, dirs_exist_ok=True)
        return output
    if wants_directory or os.path.isdir(output):
        os.makedirs(output, exist_ok=True)
        destination = os.path.join(output, os.path.basename(source_path))
    else:
        parent = os.path.dirname(output)
        if parent:
            os.makedirs(parent, exist_ok=True)
        destination = output
    shutil.copy2(source_path, destination)
    return destination

