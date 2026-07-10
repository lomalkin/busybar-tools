from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional
from zipfile import ZipFile

from busybar_tools.api import BusybarApiClient
from busybar_tools.report.models import ReportManifest
from busybar_tools.report.redaction import redact_text_bytes


def _log_level(line: str) -> Optional[str]:
    match = re.search(r"\[([EWD])\]\[[^\]]+\]", line)
    if match:
        return match.group(1)
    upper = line.upper()
    if "ERROR" in upper or "[E]" in upper:
        return "E"
    if "WARNING" in upper or "[W]" in upper:
        return "W"
    return None


def extract_log_findings(log_text: str) -> dict:
    errors = []
    warnings = []
    for line in log_text.splitlines():
        level = _log_level(line)
        if level == "E":
            errors.append(line)
        elif level == "W":
            warnings.append(line)
    return {
        "errors": errors,
        "warnings": warnings,
        "last_errors": errors[-10:],
        "last_warnings": warnings[-10:],
    }


def collect_logs(
    zipf: ZipFile,
    api: BusybarApiClient,
    manifest: ReportManifest,
    collected: Dict[str, Any],
) -> None:
    remote_path = "/ext/busybar-report.log"
    try:
        api.post_bytes("/api/log_dump", params={"path": remote_path}, data=b"")
    except Exception as exc:
        manifest.failed("logs:dump", exc)
        return

    try:
        data = redact_text_bytes(api.get_bytes("/api/storage/read", params={"path": remote_path}))
        zipf.writestr("logs/dump.log", data)
        log_findings = extract_log_findings(data.decode("utf-8", errors="replace"))
        if log_findings["errors"]:
            zipf.writestr("logs/errors.txt", "\n".join(log_findings["errors"]) + "\n")
        if log_findings["warnings"]:
            zipf.writestr("logs/warnings.txt", "\n".join(log_findings["warnings"]) + "\n")
        collected["logs/dump.log"] = {
            "bytes": len(data),
            "source": remote_path,
            "errors_count": len(log_findings["errors"]),
            "warnings_count": len(log_findings["warnings"]),
            "errors_path": "logs/errors.txt" if log_findings["errors"] else None,
            "warnings_path": "logs/warnings.txt" if log_findings["warnings"] else None,
            "last_errors": log_findings["last_errors"],
            "last_warnings": log_findings["last_warnings"],
        }
        manifest.ok("logs:dump", "logs/dump.log", f"source={remote_path}")
    except Exception as exc:
        manifest.failed("logs:read", exc)
    finally:
        try:
            api.delete_bytes("/api/storage/remove", params={"path": remote_path})
        except Exception as exc:
            logging.debug("Could not remove temporary log dump %s: %s", remote_path, exc)
