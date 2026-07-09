import logging
import os
import posixpath
import time

from busybar_tools.config import DIR_BSB_RECOVERY, DIR_BSB_TMP_UPDATE
from busybar_tools.device import wait_for_device_maybe
from busybar_tools.flipper.cli import Cli
from busybar_tools.flipper.storage_socket import FlipperStorage


def _flipper_mkdir_p(storage, path):
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = "/" + path

    cur = ""
    for part in path.split("/"):
        if part == "":
            cur = "/"
            continue
        cur = "/" + part if cur == "/" else cur + "/" + part
        if not storage.exist_dir(cur):
            logging.info(f"Creating {cur} on device...")
            storage.mkdir(cur)


def busybar_storage_upload_dir_to_device(device, dir_src, dir_dst, unlock_bkp=False):
    try:
        if unlock_bkp:
            with Cli(device) as cli:
                logging.info("Enabling debug mode...")
                cli.send("sysctl debug 1\r")
                logging.info("Unlocking /bkp...")
                cli.send("sysctl storage_bkp_unlock 1\r")

        with FlipperStorage(device) as storage:
            logging.info(f"Uploading {dir_src} to {dir_dst} @ {device[0]}:{device[1]}...")
            _flipper_mkdir_p(storage, dir_dst)

            for root, dirs, files in os.walk(dir_src):
                for dir_name in dirs:
                    local_dir = os.path.join(root, dir_name)
                    rel_path = os.path.relpath(local_dir, dir_src)
                    device_dir = f"{dir_dst}/{rel_path.replace(os.sep, '/')}"
                    _flipper_mkdir_p(storage, device_dir)

                for file_name in files:
                    local_file = os.path.join(root, file_name)
                    rel_path = os.path.relpath(local_file, dir_src)
                    device_file = f"{dir_dst}/{rel_path.replace(os.sep, '/')}"
                    parent = posixpath.dirname(device_file)
                    if parent:
                        _flipper_mkdir_p(storage, parent)

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
            device_files = {}
            for root, _, files in storage.walk(dir_dst):
                for file in files:
                    file_path = os.path.join(root, file).replace(os.sep, "/")
                    rel_path = file_path.replace(dir_dst, "").lstrip("/")
                    try:
                        device_files[rel_path] = storage.size(file_path)
                    except Exception:
                        logging.warning(f"Could not get size of {file_path} on device")

            all_match = True
            for root, _, files in os.walk(dir_src):
                for file in files:
                    local_file = os.path.join(root, file)
                    rel_path = os.path.relpath(local_file, dir_src).replace(os.sep, "/")
                    if rel_path not in device_files:
                        logging.error(f"{rel_path}: not found on device")
                        all_match = False
                        continue
                    device_size = device_files[rel_path]
                    local_size = os.path.getsize(local_file)
                    if local_size == device_size:
                        logging.info(f"{rel_path}: {local_size} bytes")
                    else:
                        logging.error(f"{rel_path}: local={local_size}, device={device_size}")
                        all_match = False

            if all_match:
                logging.info("All files verified successfully!")
                return True
            logging.error("Some files do not match!")
            return False
    except Exception as e:
        logging.error(f"Verification failed: {e}")
        return False


def busybar_storage_upload_auto(args, unpacked_bundle_dir, save_as_recovery=False, warning_timeout=3):
    logging.info("Running update via storage...")

    dir_dst = DIR_BSB_TMP_UPDATE
    unlock_bkp = False
    if save_as_recovery:
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

