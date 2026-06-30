#!/usr/bin/env python3
import os, sys, time
import shutil, platform
import subprocess

import posixpath
from urllib import request
import logging

from urllib.parse import urlparse

from busybar_tools.helpers import (
    fetch_url, print_pretty, file_download, busybar_workdir_get, url_to_dir_name, busybar_api_update, busybar_update_get_index_file_name, busybar_update_url_normalize, busybar_update_parse_index, file_sha256, wait_for_device
)

from busybar_tools.bsb_term import run_session

from busybar_tools.bsb_lite import BSB_Lite

from busybar_tools.config import DIR_BSB_TMP_UPDATE, TCP_TIMEOUT_DEFAULT, DIR_BSB_TMP, DIR_BSB_RECOVERY, UPDATE_MANIFEST_FILE

from busybar_tools.flipper.cli import Cli
from busybar_tools.flipper.storage_socket import FlipperStorage

UNPACKED_DIR_NAME = "unpacked"


def wait_for_device_maybe(args):
    """Wait for the device to be reachable, unless --no-wait was passed."""
    if getattr(args, "no_wait", False):
        logging.info("Skipping device reachability check (--no-wait).")
        return
    wait_for_device(args.device, verbose=getattr(args, "verbose", True))

def busybar_storage_upload_dir_to_device(device, dir_src, dir_dst, unlock_bkp=False):
    def flipper_mkdir_p(storage, path: str):
        """Create directory and parents on Flipper (mkdir -p semantics).

        Uses posix-style path operations so it works correctly for the device.
        """
        # Normalize and ensure absolute-like path
        path = posixpath.normpath(path)
        if not path.startswith("/"):
            path = "/" + path

        # Walk components and create missing directories
        parts = path.split("/")
        cur = ""
        for part in parts:
            if part == "":
                cur = "/"
                continue
            if cur == "/":
                cur = "/" + part
            else:
                cur = cur + "/" + part

            try:
                if not storage.exist_dir(cur):
                    logging.info(f"Creating {cur} on device...")
                    storage.mkdir(cur)
            except Exception as e:
                # Re-raise with context so caller can handle/abort
                raise
    try:
        if unlock_bkp:
            with Cli(device) as cli:
                logging.info("Enabling debug mode...")
                cli.send("sysctl debug 1\r")
                logging.info("Unlocking /bkp...")
                cli.send("sysctl storage_bkp_unlock 1\r")

        with FlipperStorage(device) as storage:
            logging.info(f"Uploading {dir_src} to {dir_dst} @ {device[0]}:{device[1]}...")

            # Ensure target dir and parents exist (mkdir -p semantics)
            flipper_mkdir_p(storage, dir_dst)

            for root, dirs, files in os.walk(dir_src):
                # Create subdirectories
                for dir_name in dirs:
                    local_dir = os.path.join(root, dir_name)
                    rel_path = os.path.relpath(local_dir, dir_src)
                    device_dir = f"{dir_dst}/{rel_path.replace(os.sep, '/')}"

                    flipper_mkdir_p(storage, device_dir)

                # Upload files
                for file_name in files:
                    local_file = os.path.join(root, file_name)
                    rel_path = os.path.relpath(local_file, dir_src)
                    device_file = f"{dir_dst}/{rel_path.replace(os.sep, '/')}"

                    # Make sure parent dir exists before sending file
                    parent = posixpath.dirname(device_file)
                    if parent and parent != "":
                        flipper_mkdir_p(storage, parent)

                    size = os.path.getsize(local_file)
                    logging.info(f"Uploading {device_file} ({size} bytes) to device...")
                    storage.send_file(local_file, device_file)

        return True

    except Exception as e:
        logging.error(f"Upload failed: {e}")
        return False
    finally:
        try:
            if unlock_bkp:
                with Cli(device) as cli:
                    logging.info("Locking /bkp...")
                    cli.send("sysctl storage_bkp_unlock 0\r")
                
                    logging.info("Disabling debug mode...")
                    cli.send("sysctl debug 0\r")
        except Exception:
            pass

def busybar_storage_verify_dir_on_device(device, dir_src, dir_dst):
    try:
        with FlipperStorage(device) as storage:
            logging.info(f"Verifying {dir_dst} on device against {dir_src}...")

            # Collect device file info
            device_files = {}
            for root, _, files in storage.walk(dir_dst):
                for file in files:
                    file_path = os.path.join(root, file).replace(os.sep, "/")
                    rel_path = file_path.replace(dir_dst, "").lstrip("/")

                    try:
                        size = storage.size(file_path)
                        device_files[rel_path] = size
                    except Exception:
                        logging.warning(f"Could not get size of {file_path} on device")

            # Compare with local files
            all_match = True
            for root, _, files in os.walk(dir_src):
                for file in files:
                    local_file = os.path.join(root, file)
                    # Normalize to forward slashes so keys match the device side (which uses '/');
                    # on Windows os.path.relpath returns backslash-separated paths.
                    rel_path = os.path.relpath(local_file, dir_src).replace(os.sep, "/")

                    if rel_path in device_files:
                        device_size = device_files[rel_path]
                        local_size = os.path.getsize(local_file)

                        if local_size == device_size:
                            logging.info(f"✓ {rel_path}: {local_size} bytes")
                        else:
                            logging.error(
                                f"✗ {rel_path}: local={local_size}, device={device_size}"
                            )
                            all_match = False
                    else:
                        logging.error(f"✗ {rel_path}: not found on device")
                        all_match = False

            if all_match:
                logging.info("✓ All files verified successfully!")
                return True
            else:
                logging.error("✗ Some files do not match!")
                return False

    except Exception as e:
        logging.error(f"Verification failed: {e}")
        return False

def bsb_sysctl_debug_enable(device, port):
    logging.info("Try to enable debug mode...")

    try:
        bsb = BSB_Lite((device, port))
        bsb.start()
        res = bsb.sysctl_debug(1)
        print_pretty(res)
        return True
    except Exception as e:
        logging.error(f"Failed to enable debug mode: {e}")
        return False

def bsb_invoke_update(device, port, file_path):
    logging.info("Try to invoke update via API...")

    try:
        bsb = BSB_Lite((device, port))
        bsb.start()
        res = bsb.cmd_oneshot(f"update install {file_path}/{UPDATE_MANIFEST_FILE}", timeout = 3)
        print_pretty(res)
        return True
    except Exception as e:
        logging.error(f"Failed to invoke update: {e}")
        return False

def _run_cli_batch(args, cmds):
    """Run a list of CLI commands non-interactively over a single connection."""
    timeout = getattr(args, "timeout", 5)
    try:
        with BSB_Lite((args.device, args.port)) as bsb:
            for cmd in cmds:
                logging.info(f"> {cmd}")
                for line in bsb.cmd_oneshot(cmd, timeout=timeout):
                    print(line)
        return 0
    except Exception as e:
        logging.error(f"CLI batch failed: {e}")
        return 1


def run_cli_terminal(args):
    # Resolve commands passed as arguments after `--` (joined into a single command line).
    cli_args = list(getattr(args, "cli_args", []) or [])
    if cli_args and cli_args[0] == "--":
        cli_args = cli_args[1:]
    args_cmd = " ".join(cli_args).strip()
    interactive = getattr(args, "interactive", False)

    wait_for_device_maybe(args)

    if args_cmd:
        if interactive:
            if sys.stdin.isatty():
                logging.info("Running command, then staying in the interactive session...")
                run_session(args.device, args.port, tcp_timeout=TCP_TIMEOUT_DEFAULT, prelude=args_cmd)
                return 0
            logging.warning("-i requires an interactive terminal (stdin is not a TTY); running command and exiting.")
        return _run_cli_batch(args, [args_cmd])

    # No command in arguments: read from stdin if it's piped, else go interactive.
    if not sys.stdin.isatty():
        if interactive:
            logging.warning("-i is ignored when commands are read from stdin; exiting after running them.")
        cmds = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
        if not cmds:
            return 0
        return _run_cli_batch(args, cmds)

    logging.info("Running CLI terminal...")
    print(f"Connecting to {args.device}:{args.port} with timeout {TCP_TIMEOUT_DEFAULT}s...")
    print("Press Ctrl+] to exit.")
    run_session(args.device, args.port, tcp_timeout=TCP_TIMEOUT_DEFAULT)
    return 0

def busybar_get_index_by_url(base_url, target, work_dir):
    index_name = busybar_update_get_index_file_name(target)
    index_url = f"{base_url}{index_name}"

    try:
        index_data = fetch_url(index_url, timeout=10)
        if not index_data:
            raise Exception(f"Failed to fetch index {index_url}")
        else:
            logging.info(f"Fetched index content from {index_url}, length: {len(index_data)} bytes")
    except Exception as e:
        index_data = None
        logging.warning(f"{e}")
        logging.info("Trying to use cached index...")

    index_path = os.path.join(work_dir, index_name)
    if index_data:
        try:
            with open(index_path, 'w') as f:
                f.write(index_data)
            logging.info(f"Index content saved to {index_path}")
        except Exception as e:
            logging.error(f"Error saving index content: {e}")
    else:
        try:
            with open(index_path, 'r') as f:
                index_data = f.read()
            logging.info(f"Loaded index content from cache {index_path}")
        except Exception as e:
            logging.error(f"Error loading index content from cache: {e}")
            return 1

    index_parsed = busybar_update_parse_index(index_data, base_url)
    # print_pretty(index_parsed)
    return index_parsed


def busybar_download_file_by_filetype(source_url, file_type, work_dir, index_parsed):
    logging.info(f"Trying for file_type {file_type}...")

    file_path = None
    for file in index_parsed:
        if file["file_type"] == file_type:
            file_path = os.path.join(work_dir, file['file_name'])

            if not os.path.exists(file_path):
                file_path = file_download(file["file_url"], file['file_name'], work_dir, progress=True)
            
            file_hash = file_sha256(file_path)

            if file_hash != file["sha256sum"]:
                logging.warning(f"File Hash check failed: {file['file_name']}")
                file_path = file_download(file["file_url"], file['file_name'], work_dir, progress=True)
                file_hash = file_sha256(file_path)

            if file_hash == file["sha256sum"]:
                logging.info(f"Hash check passed: {file['file_name']}: {file['sha256sum']}")
            else:
                logging.error(f"File Hash check failed ONCE AGAIN: {file['file_name']}: {file['sha256sum']}")
            break
    if file_path is None:
        logging.warning(f"Failed to find file of type {file_type} in index!")
    
    return file_path

def resolve_source(args):
    """Determine the firmware source and download it if needed.

    Priority order (first match wins):
      1. existing local file       -> (source_file, None)
      2. existing local directory  -> (None, source_dir)   # already-unpacked bundle
      3. otherwise treat the string as a URL / tag / branch of the update server,
         build the URL and download the matching bundle -> (source_file, None)

    An explicit http/https URL naturally lands in branch 3, since it is neither a
    local file nor a local dir. Exactly one of the returned values is set.
    Raises RuntimeError if a remote bundle could not be found/downloaded.
    """
    if os.path.isfile(args.source):
        source_file = os.path.abspath(args.source)
        logging.info(f"Considering source as FILE: {args.source} -> {source_file}")
        return source_file, None

    if os.path.isdir(args.source):
        source_dir = os.path.abspath(args.source)
        logging.info(f"Considering source as DIR: {args.source} -> {source_dir}")
        return None, source_dir

    # URL / tag / branch of the update server.
    args.source_url = busybar_update_url_normalize(args.source)
    logging.info(f"Considering source as URL/tag/branch: {args.source} -> {args.source_url}")

    # Craft file_type, "(update|bkp)[_signed]_(tgz|tar)"
    file_type = f"{args.update_bundle_type}"
    if args.signed:
        file_type += "_signed"

    if getattr(args, "save_as_recovery", False) and args.update_bundle_type != "bkp":
        logging.warning(
            f"--save-as-recovery is normally used with --bkp (the bundle type designed for the "
            f"recovery partition); proceeding with '{args.update_bundle_type}' bundle anyway."
        )

    work_dir = busybar_workdir_get(url_to_dir_name(args.source_url))
    index_parsed = busybar_get_index_by_url(args.source_url, args.target, work_dir)

    source_file = None
    try:
        source_file = busybar_download_file_by_filetype(args.source_url, f"{file_type}_tgz", work_dir, index_parsed)
    except Exception as e:
        logging.error(f"Failed to get file by type {file_type}_tgz: {e}")
    # Fallback to _tar if _tgz not found
    if source_file is None:
        try:
            source_file = busybar_download_file_by_filetype(args.source_url, f"{file_type}_tar", work_dir, index_parsed)
        except Exception as e:
            logging.error(f"Failed to get file by type {file_type}_tar: {e}")

    if source_file is None:
        raise RuntimeError(f"No suitable update file ({file_type}_tgz/_tar) found in index for {args.source_url}")

    return source_file, None


def unpack_bundle(source_file):
    """Unpack a bundle archive into a clean work dir; return the unpacked dir path."""
    work_dir = busybar_workdir_get("local_file")
    unpacked_bundle_dir = os.path.join(work_dir, UNPACKED_DIR_NAME)
    # Clean up work dir before unpack to avoid confusion with old files
    shutil.rmtree(unpacked_bundle_dir, ignore_errors=True)
    assert bundle_unpack(source_file, unpacked_bundle_dir) == 0
    return unpacked_bundle_dir


def _place_result(src_path, output):
    """Copy a fetched file/dir to `output` (a dir or a file path); return the final path.

    If `output` is falsy, leave the result in the cache and return src_path as-is.
    """
    if not output:
        return src_path

    # Note the trailing-slash intent before abspath() strips it.
    wants_dir = output.endswith(("/", os.sep))
    output = os.path.abspath(os.path.expanduser(output))

    if os.path.isdir(src_path):
        os.makedirs(output, exist_ok=True)
        shutil.copytree(src_path, output, dirs_exist_ok=True)
        return output

    # src is a file: treat trailing-slash / existing dir as a destination directory.
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


def _device_info_ready(info, required_keys):
    """True if all required device_info keys are present and non-empty."""
    return all(info.get(k) for k in required_keys)


def device_read_info(device, port, retries=1, delay=1, required_keys=None):
    """Connect to the device CLI and return the parsed device_info dict.

    Retries both on connection errors AND, when `required_keys` is given, until those keys
    are populated: after a reboot the U5 CLI answers quickly but the SL co-processor reports
    its fields (sl_firmware_*, sl_intercom_status) a bit later, so a bare read can return a
    partial dict. If the data is still incomplete once retries are exhausted, the last partial
    dict is returned (with a warning) rather than failing. Raises only if no read ever succeeded.
    """
    last_info = None
    last_err = None
    for attempt in range(retries):
        try:
            with BSB_Lite((device, port)) as bsb:
                info = bsb.device_info()
            last_info = info
            if not required_keys or _device_info_ready(info, required_keys):
                return info
            missing = [k for k in required_keys if not info.get(k)]
            logging.debug(f"device_info incomplete (missing {missing}), attempt {attempt + 1}/{retries}")
        except Exception as e:
            last_err = e
            logging.debug(f"device_info attempt {attempt + 1}/{retries} failed: {e}")
        if attempt + 1 < retries:
            time.sleep(delay)

    if last_info is not None:
        if required_keys and not _device_info_ready(last_info, required_keys):
            logging.warning("device_info still incomplete after retries; reporting partial data.")
        return last_info
    raise RuntimeError(f"Failed to read device_info from {device}:{port}: {last_err}")


def _device_info_bool(info, key):
    val = info.get(key)
    if val is None:
        raise RuntimeError(f"device_info is missing '{key}'")
    return str(val).strip().lower() == "true"


def device_info_target(info):
    """Hardware target (20/21/22) reported by the device."""
    try:
        return int(info["u5_firmware_target"])
    except (KeyError, ValueError):
        raise RuntimeError("Could not read hardware target (u5_firmware_target) from device_info")


def device_info_signed(info):
    """Whether the device runs signed firmware (secure boot enabled on both cores).

    sl_nwp_signature and sl_m4_signature must agree; an inconsistent state is an error.
    """
    nwp = _device_info_bool(info, "sl_nwp_signature")
    m4 = _device_info_bool(info, "sl_m4_signature")
    if nwp != m4:
        raise RuntimeError(
            f"Inconsistent secure boot state (sl_nwp_signature={nwp}, sl_m4_signature={m4}); "
            "cannot decide signed/unsigned automatically."
        )
    return nwp


_VERSION_FIELDS = (
    "u5_firmware_branch", "u5_firmware_commit", "u5_firmware_builddate",
    "sl_firmware_branch", "sl_firmware_commit", "sl_firmware_builddate",
)

# Fields needed to autodetect target & signing (also gate "device fully booted").
_DETECT_FIELDS = ("u5_firmware_target", "sl_nwp_signature", "sl_m4_signature")


def device_version_fingerprint(info):
    """Tuple of version-identifying fields, for before/after comparison."""
    return tuple(info.get(k, "?") for k in _VERSION_FIELDS)


def format_version(info):
    """Human-readable firmware version string from device_info."""
    return (
        f"u5 {info.get('u5_firmware_branch', '?')}@{info.get('u5_firmware_commit', '?')} "
        f"({info.get('u5_firmware_builddate', '?')}), "
        f"sl {info.get('sl_firmware_branch', '?')}@{info.get('sl_firmware_commit', '?')} "
        f"({info.get('sl_firmware_builddate', '?')})"
    )


def run_auto_install(args):
    """High-level automatic install for regular users.

    Reads device_info to autodetect the hardware target and whether signed firmware is required,
    fetches the matching regular update bundle from the update server, installs it, waits for the
    device to reboot and reports the version change.

    Only update-server sources (tag/branch/URL) are supported: a local file/dir would bypass the
    target/signed autodetection.
    """
    if os.path.isfile(args.source) or os.path.isdir(args.source):
        logging.error(
            f"auto-install works only with an update-server tag/branch or URL, not a local "
            f"file/directory ('{args.source}'). Use 'install' for a local source."
        )
        return 1

    wait_for_device_maybe(args)

    logging.info(f"Reading device info from {args.device}:{args.port}...")
    info_before = device_read_info(
        args.device, args.port,
        retries=5, delay=2, required_keys=_VERSION_FIELDS + _DETECT_FIELDS,
    )

    target = device_info_target(info_before)
    signed = device_info_signed(info_before)
    logging.info(
        f"Detected: target {target}, {'signed' if signed else 'unsigned'} firmware. "
        f"Current version: {format_version(info_before)}"
    )

    # Drive the regular install pipeline from the autodetected values.
    args.target = target
    args.signed = signed
    args.update_bundle_type = "update"
    args.invoke_update = True

    ret = run_install(args)
    if ret:
        return ret
    
    if getattr(args, "no_wait_after", False):
        logging.info("Skipping device reachability check after install (--no-wait-after).")
        return 0

    logging.info("Waiting for the device to reboot and come back...")
    # First let it go offline (bounded), then wait for it to be reachable again.
    wait_for_device(args.device, timeout=60, verbose=args.verbose, success_ping_as=False)
    wait_for_device(args.device, verbose=args.verbose)

    info_after = device_read_info(
        args.device, args.port,
        retries=20, delay=2, required_keys=_VERSION_FIELDS,
    )

    if device_version_fingerprint(info_before) == device_version_fingerprint(info_after):
        print(f"Already up to date — reinstalled the same build:\n  {format_version(info_after)}")
    else:
        print(f"Updated from:\n  {format_version(info_before)}\nto:\n  {format_version(info_after)}")
    print("Done. You are magnificent! ✨")
    return 0


def run_install(args, verbose=False):
    if verbose:
        for arg, value in vars(args).items():
            print(f"\t{arg}: {value}")

    source_file, source_dir = resolve_source(args)
    args.source_file = source_file
    args.source_dir = source_dir

    if source_file:
        # HTTP transport installs the archive directly, without a local unpack.
        if args.via_storage == False:
            return run_update_via_http(args)
        source_dir = unpack_bundle(source_file)
        args.source_dir = source_dir

    if source_dir:
        return _install_from_dir(args, source_dir)

    return 0


def _install_from_dir(args, source_dir):
    invoke_update = args.invoke_update
    if invoke_update == False:
        logging.warning("Will NOT invoke update after uploading the bundle on device!")

    bsb_update_dst_dir = busybar_storage_upload_auto(args, source_dir)

    if invoke_update:
        return run_update_from_storage(args, bsb_update_dst_dir)
    return 0


def run_write_recovery(args):
    """Write a firmware bundle into the device recovery partition (/bkp), without installing it.

    Reuses the shared acquisition stages (resolve_source + unpack_bundle) and uploads to the
    recovery partition via storage. Installation is never invoked.
    """
    args.save_as_recovery = True  # also drives the "--bkp recommended" warning in resolve_source
    source_file, source_dir = resolve_source(args)
    if source_file is not None:
        source_dir = unpack_bundle(source_file)

    if not source_dir:
        logging.error("Could not obtain a bundle directory to write to recovery.")
        return 1

    busybar_storage_upload_auto(args, source_dir, save_as_recovery=True, warning_timeout=args.confirm_timeout)
    return 0


def run_fetch(args):
    """Fetch a firmware bundle locally without touching the device.

    Reuses resolve_source (+ unpack_bundle) shared with install.
    Without --unpack: download only. With --unpack: download and unpack.
    Result is placed into --output if given, otherwise left in the cache.
    The final path is printed to stdout.
    """
    source_file, source_dir = resolve_source(args)

    if getattr(args, "unpack", False):
        # A directory source is already unpacked; otherwise unpack the bundle file.
        result = unpack_bundle(source_file) if source_file is not None else source_dir
    else:
        # Download-only: prefer the bundle file; a directory source has nothing to fetch.
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

def run_update_via_http(args):
    logging.info("Using HTTP transport for update...")
    wait_for_device_maybe(args)
    bsb_sysctl_debug_enable(args.device, args.port)
    return busybar_api_update(args.device, args.source_file)

def run_update_from_storage(args, update_dir):
    logging.info(f"Running update via storage from {update_dir}...")

    wait_for_device_maybe(args)

    assert bsb_sysctl_debug_enable(args.device, args.port), "Failed to enable debug mode!"
    assert bsb_invoke_update(args.device, args.port, update_dir), "Failed to invoke update via CLI!"

    return 0

def run_update_from_recovery(args):
    return run_update_from_storage(args, DIR_BSB_RECOVERY)

def run_update_local(args):
    target = args.device_path
    if target == "recovery":
        return run_update_from_recovery(args)
    if not target:
        target = DIR_BSB_TMP_UPDATE
    return run_update_from_storage(args, target)

def bundle_unpack(source_file, unpack_dir):
    logging.info(f"Unpacking update bundle {source_file} to {unpack_dir}...")
    try:
        shutil.unpack_archive(source_file, unpack_dir)
        logging.info(f"Unpacked: {os.listdir(unpack_dir)}")
        return 0
    except Exception as e:
        logging.error(f"Failed to unpack bundle: {e}")
        return 1

def busybar_storage_upload_auto(args, unpacked_bundle_dir, save_as_recovery=False, warning_timeout=3):
    logging.info("Running update via storage...")

    dir_dst = DIR_BSB_TMP_UPDATE
    unlock_bkp = False
    if save_as_recovery == True:
        logging.warning("Danger! Saving update bundle as recovery bundle on device /bkp!")
        for i in range(warning_timeout):
            logging.warning(f"You have {warning_timeout - i} seconds to Cancel (Ctrl+C)...")
            time.sleep(1)
        dir_dst = DIR_BSB_RECOVERY
        unlock_bkp = True
    
    wait_for_device_maybe(args)

    busybar_storage_upload_dir_to_device((args.device, args.port), unpacked_bundle_dir, dir_dst, unlock_bkp=unlock_bkp)

    assert busybar_storage_verify_dir_on_device((args.device, args.port), unpacked_bundle_dir, dir_dst), "Verification failed after upload!"

    return dir_dst

def run_storage(args):
    wait_for_device_maybe(args)
    # storage.py located in current package.
    # we invoke it as external command and pass all args to it, so it can handle the storage operations.
    # Use sys.executable so the same interpreter (and its installed deps) is used —
    # critical when busybar is installed via pipx into an isolated venv, since plain
    # `python3` would resolve to the system interpreter without our dependencies.
    # `-m` resolves the module via sys.path, so this is independent of the current working directory.
    # print_pretty(args)
    # Map busybar device selection onto storage.py: --device -> --host, --port -> -p (TCP port).
    # These must precede the storage.py sub-command, so prepend them and drop a leading "--".
    device_args = [
        "--host", args.device,
        "-p", str(args.port),
    ]
    storage_args = list(args.storage_args)
    if storage_args and storage_args[0] == "--":
        storage_args = storage_args[1:]
    cmd = [sys.executable, "-m", "busybar_tools.storage"] + device_args + storage_args
    logging.info(f"Invoking command: {' '.join(cmd)}")
    return subprocess.call(cmd)

def run_wait_for_device(args):
    wait_for_device_maybe(args)

def run_clean(args):
    dir = busybar_workdir_get()
    print(f"Cleaning up {dir}...")

    try:
        shutil.rmtree(dir, ignore_errors=True)
    except Exception as e:
        logging.error(f"Error cleaning up {dir}: {e}")
        return 1

    return 0

