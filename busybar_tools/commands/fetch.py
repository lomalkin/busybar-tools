import logging
import os

from busybar_tools.firmware import _place_result, resolve_source, unpack_bundle


def run_fetch(args):
    """Fetch a firmware bundle locally without touching the device."""
    source_file, source_dir = resolve_source(args)

    if getattr(args, "unpack", False):
        result = unpack_bundle(source_file) if source_file is not None else source_dir
    else:
        result = source_file if source_file is not None else source_dir

    output = getattr(args, "output", None)
    result = _place_result(result, output)
    if output:
        action = "Fetched and unpacked" if getattr(args, "unpack", False) else "Fetched"
        logging.info(f"{action} '{args.source}' to: {result}")
    print(result)

    if getattr(args, "unpack", False):
        logging.info(f"Contents of unpacked bundle '{result}':")
        for root, dirs, files in os.walk(result):
            for name in files:
                file_path = os.path.join(root, name)
                rel_path = os.path.relpath(file_path, result)
                size = os.path.getsize(file_path)
                print(f"\t{rel_path} ({size} bytes)")
    return 0


__all__ = ["run_fetch"]
