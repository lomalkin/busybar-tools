"""Public API for busybar-tools.

Command internals live in ``busybar_tools.commands`` and domain helpers live in
their own modules. This package facade intentionally exports only stable,
non-private entry points.
"""

from busybar_tools.commands.auto_install import run_auto_install
from busybar_tools.commands.cli_terminal import run_cli_terminal
from busybar_tools.commands.fetch import run_fetch
from busybar_tools.commands.install import (
    run_install,
    run_update_from_recovery,
    run_update_from_storage,
    run_update_local,
    run_update_via_http,
    run_write_recovery,
)
from busybar_tools.commands.recover import run_recover
from busybar_tools.commands.storage import run_storage
from busybar_tools.commands.wait import run_clean, run_wait_for_device
from busybar_tools.config import DIR_BSB_RECOVERY, DIR_BSB_TMP_UPDATE
from busybar_tools.device import (
    bsb_invoke_update,
    bsb_sysctl_debug_enable,
    device_info_signed,
    device_info_target,
    device_read_info,
    device_version_fingerprint,
    format_version,
    wait_for_device_maybe,
)
from busybar_tools.firmware import (
    bundle_unpack,
    busybar_download_file_by_filetype,
    busybar_get_index_by_url,
    resolve_source,
    unpack_bundle,
)
from busybar_tools.storage_ops import (
    busybar_storage_upload_auto,
    busybar_storage_upload_dir_to_device,
    busybar_storage_verify_dir_on_device,
)

__all__ = [
    "DIR_BSB_RECOVERY",
    "DIR_BSB_TMP_UPDATE",
    "bsb_invoke_update",
    "bsb_sysctl_debug_enable",
    "bundle_unpack",
    "busybar_download_file_by_filetype",
    "busybar_get_index_by_url",
    "busybar_storage_upload_auto",
    "busybar_storage_upload_dir_to_device",
    "busybar_storage_verify_dir_on_device",
    "device_info_signed",
    "device_info_target",
    "device_read_info",
    "device_version_fingerprint",
    "format_version",
    "resolve_source",
    "run_auto_install",
    "run_clean",
    "run_cli_terminal",
    "run_fetch",
    "run_install",
    "run_recover",
    "run_storage",
    "run_update_from_recovery",
    "run_update_from_storage",
    "run_update_local",
    "run_update_via_http",
    "run_wait_for_device",
    "run_write_recovery",
    "unpack_bundle",
    "wait_for_device_maybe",
]
