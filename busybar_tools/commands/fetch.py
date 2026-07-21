import logging
import os

from busybar_tools.firmware import place_result, resolve_source, unpack_bundle
from busybar_tools.options import FetchOptions


def run_fetch(options: FetchOptions):
    """Fetch a firmware bundle locally without touching the device."""
    source_file, source_dir = resolve_source(options.firmware)

    if options.unpack:
        result = unpack_bundle(source_file) if source_file is not None else source_dir
    else:
        result = source_file if source_file is not None else source_dir

    result = place_result(result, options.output)
    if options.output:
        action = "Fetched and unpacked" if options.unpack else "Fetched"
        logging.info(f"{action} '{options.firmware.source}' to: {result}")
    print(result)

    if options.unpack:
        logging.info(f"Contents of unpacked bundle '{result}':")
        for root, _, files in os.walk(result):
            for name in files:
                file_path = os.path.join(root, name)
                rel_path = os.path.relpath(file_path, result)
                size = os.path.getsize(file_path)
                print(f"\t{rel_path} ({size} bytes)")
    return 0


__all__ = ["run_fetch"]
