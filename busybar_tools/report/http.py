from __future__ import annotations

from typing import Any, Dict
from zipfile import ZipFile

from busybar_tools.api import BusybarApiClient
from busybar_tools.report.models import ReportManifest
from busybar_tools.report.redaction import redact
from busybar_tools.report.util import write_json

JSON_ENDPOINTS = [
    ("api/version.json", "/api/version", None),
    ("api/transport.json", "/api/transport", None),
    ("api/status.json", "/api/status", None),
    ("api/status_device.json", "/api/status/device", None),
    ("api/status_firmware.json", "/api/status/firmware", None),
    ("api/status_system.json", "/api/status/system", None),
    ("api/status_power.json", "/api/status/power", None),
    ("api/time.json", "/api/time", None),
    ("api/timezone.json", "/api/time/timezone", None),
    ("api/wifi_status.json", "/api/wifi/status", None),
    ("api/ble_status.json", "/api/ble/status", None),
    ("api/update_status.json", "/api/update/status", None),
    ("api/update_autoupdate.json", "/api/update/autoupdate", None),
    ("api/name.json", "/api/name", None),
    ("api/access.json", "/api/access", None),
    ("api/display_brightness.json", "/api/display/brightness", None),
    ("api/audio_volume.json", "/api/audio/volume", None),
    ("api/storage_status.json", "/api/storage/status", None),
    ("api/busy_snapshot.json", "/api/busy/snapshot", None),
    ("api/smart_home_pairing.json", "/api/smart_home/pairing", None),
]


def collect_json_endpoints(
    zipf: ZipFile,
    api: BusybarApiClient,
    manifest: ReportManifest,
    collected: Dict[str, Any],
) -> None:
    for archive_path, endpoint, params in JSON_ENDPOINTS:
        name = f"http:{endpoint}"
        try:
            data = redact(api.get_json(endpoint, params=params))
            collected[archive_path] = data
            write_json(zipf, archive_path, data)
            manifest.ok(name, archive_path)
        except Exception as exc:
            manifest.failed(name, exc)
