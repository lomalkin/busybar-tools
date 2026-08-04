from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

from busybar_tools.report.models import ReportManifest, ReportOptions
from busybar_tools.report.redaction import redact


def _get(data: dict, *keys, default=None):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _first(data: dict, *paths):
    for path in paths:
        value = _get(data, *path)
        if value not in (None, "", [], {}):
            return value
    return None


def _parse_device_info(lines: List[str]) -> dict:
    parsed = {}
    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            parsed[key.strip()] = value.strip()
    return redact(parsed)


def build_summary(options: ReportOptions, manifest: ReportManifest, collected: Dict[str, Any]) -> dict:
    device_info = _parse_device_info(_get(collected, "cli", "device_info", "lines", default=[]))
    status = collected.get("api/status.json", {})
    firmware = collected.get("api/status_firmware.json", {})
    power = collected.get("api/status_power.json", {})
    storage = collected.get("api/storage_status.json", {})
    wifi = collected.get("api/wifi_status.json", {})
    ble = collected.get("api/ble_status.json", {})
    update = collected.get("api/update_status.json", {})
    logs = collected.get("logs/dump.log", {})

    failed = [item for item in manifest.collectors if item.get("status") == "failed"]
    skipped = [item for item in manifest.collectors if item.get("status") == "skipped"]
    firmware_status = firmware
    if not firmware_status and isinstance(status, dict):
        firmware_status = status.get("firmware")

    summary = {
        "created_at": manifest.created_at,
        "tool": {
            "name": manifest.tool,
            "version": manifest.tool_version,
            "python": sys.version.split()[0],
        },
        "device": {
            "host": options.endpoint.host,
            "http_port": options.http_port,
            "cli_port": options.endpoint.port,
            "name": _first(collected, ("api/name.json", "name"), ("api/name.json", "value")),
            "transport": _get(collected, "api/transport.json", "type"),
            "api_semver": _get(collected, "api/version.json", "api_semver"),
            "target": device_info.get("u5_firmware_target"),
        },
        "firmware": {
            "status": firmware_status,
            "device_info": {
                "u5_branch": device_info.get("u5_firmware_branch"),
                "u5_commit": device_info.get("u5_firmware_commit"),
                "u5_builddate": device_info.get("u5_firmware_builddate"),
                "sl_branch": device_info.get("sl_firmware_branch"),
                "sl_commit": device_info.get("sl_firmware_commit"),
                "sl_builddate": device_info.get("sl_firmware_builddate"),
            },
        },
        "power": power,
        "wifi": wifi,
        "ble": ble,
        "update": update,
        "storage": storage,
        "artifacts": {
            "logs": logs,
            "runtime": {
                "u5_top": _get(collected, "cli", "top_u5", "path"),
                "si917_top": _get(collected, "cli", "top_917", "path"),
                "free": _get(collected, "cli", "free", "path"),
                "help": _get(collected, "cli", "help", "path"),
            },
            "screens": collected.get("screens/meta.json"),
        },
        "collector_status": {
            "total": len(manifest.collectors),
            "failed": len(failed),
            "skipped": len(skipped),
            "failed_names": [item.get("name") for item in failed],
            "skipped_names": [item.get("name") for item in skipped],
        },
    }
    summary["findings"] = build_findings(summary)
    return summary


def _sort_findings(findings: List[dict]) -> List[dict]:
    severity_order = {"error": 0, "warning": 1, "info": 2}
    return sorted(findings, key=lambda item: severity_order.get(item.get("severity"), 99))


def build_findings(summary: dict) -> List[dict]:
    findings = []
    collectors = summary.get("collector_status", {})
    if collectors.get("failed"):
        findings.append({
            "severity": "warning",
            "title": "Some collectors failed",
            "detail": ", ".join(collectors.get("failed_names") or []),
        })

    update = summary.get("update") or {}
    check = update.get("check") if isinstance(update, dict) else {}
    if isinstance(check, dict) and check.get("status") not in (None, "", "ok", "idle"):
        detail = f"status={check.get('status')}, event={check.get('event')}"
        findings.append({"severity": "warning", "title": "Update check is not OK", "detail": detail})

    wifi = summary.get("wifi") or {}
    if isinstance(wifi, dict):
        state = wifi.get("state")
        rssi = wifi.get("rssi")
        if state and state != "connected":
            findings.append({"severity": "warning", "title": "Wi-Fi is not connected", "detail": f"state={state}"})
        if isinstance(rssi, int) and rssi < -75:
            findings.append({"severity": "warning", "title": "Weak Wi-Fi signal", "detail": f"rssi={rssi}"})

    power = summary.get("power") or {}
    if isinstance(power, dict):
        charge = power.get("battery_charge")
        if isinstance(charge, int) and charge < 20:
            findings.append({"severity": "warning", "title": "Low battery", "detail": f"battery_charge={charge}%"})

    logs = _get(summary, "artifacts", "logs", default={}) or {}
    if isinstance(logs, dict):
        if logs.get("errors_count"):
            last = logs.get("last_errors") or []
            detail = last[-1] if last else f"{logs.get('errors_count')} log errors"
            findings.append({"severity": "error", "title": "Errors found in logs", "detail": detail})
        elif logs.get("warnings_count"):
            last = logs.get("last_warnings") or []
            detail = last[-1] if last else f"{logs.get('warnings_count')} log warnings"
            findings.append({"severity": "info", "title": "Warnings found in logs", "detail": detail})

    if not findings:
        findings.append({
            "severity": "info",
            "title": "No obvious issue detected",
            "detail": "All collectors succeeded and no log errors were found.",
        })
    return _sort_findings(findings)


def _fmt_value(value) -> str:
    if value in (None, "", [], {}):
        return "n/a"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _fmt_log_artifact(logs: dict) -> str:
    if not logs:
        return "n/a"
    parts = [
        f"dump={_fmt_value(logs.get('source'))}",
        f"bytes={_fmt_value(logs.get('bytes'))}",
        f"errors={_fmt_value(logs.get('errors_count'))}",
        f"warnings={_fmt_value(logs.get('warnings_count'))}",
    ]
    if logs.get("errors_path"):
        parts.append(f"errors_path={logs['errors_path']}")
    if logs.get("warnings_path"):
        parts.append(f"warnings_path={logs['warnings_path']}")
    return ", ".join(parts)


def summary_markdown(summary: dict) -> str:
    device = summary["device"]
    firmware_info = summary["firmware"]["device_info"]
    artifacts = summary["artifacts"]
    status = summary["collector_status"]
    lines = [
        "# BUSY Bar Report",
        "",
        f"- Created: {_fmt_value(summary.get('created_at'))}",
        f"- Tool: {_fmt_value(_get(summary, 'tool', 'name'))} {_fmt_value(_get(summary, 'tool', 'version'))}, Python {_fmt_value(_get(summary, 'tool', 'python'))}",
        f"- Device: {_fmt_value(device.get('name'))} at `{device.get('host')}:{device.get('http_port')}`",
        f"- Transport: {_fmt_value(device.get('transport'))}",
        f"- API: {_fmt_value(device.get('api_semver'))}",
        f"- Target: {_fmt_value(device.get('target'))}",
        "",
        "## Firmware",
        "",
        f"- U5: {_fmt_value(firmware_info.get('u5_branch'))}@{_fmt_value(firmware_info.get('u5_commit'))} ({_fmt_value(firmware_info.get('u5_builddate'))})",
        f"- SL: {_fmt_value(firmware_info.get('sl_branch'))}@{_fmt_value(firmware_info.get('sl_commit'))} ({_fmt_value(firmware_info.get('sl_builddate'))})",
        "",
        "## Findings",
        "",
    ]
    for finding in summary.get("findings", []):
        lines.append(f"- [{_fmt_value(finding.get('severity')).upper()}] {_fmt_value(finding.get('title'))}: {_fmt_value(finding.get('detail'))}")
    lines.extend([
        "",
        "## Key State",
        "",
        f"- Power: {_fmt_value(summary.get('power'))}",
        f"- Wi-Fi: {_fmt_value(summary.get('wifi'))}",
        f"- BLE: {_fmt_value(summary.get('ble'))}",
        f"- Update: {_fmt_value(summary.get('update'))}",
        f"- Storage: {_fmt_value(summary.get('storage'))}",
        "",
        "## Artifacts",
        "",
        f"- Logs: {_fmt_log_artifact(artifacts.get('logs') or {})}",
        f"- Runtime: {_fmt_value(artifacts.get('runtime'))}",
        f"- Screens: {_fmt_value(artifacts.get('screens'))}",
        "",
        "## Collection",
        "",
        f"- Collectors: {status.get('total')}",
        f"- Failed: {status.get('failed')}",
        f"- Skipped: {status.get('skipped')}",
    ])
    if status.get("failed_names"):
        lines.extend(["", "Failed collectors:"])
        lines.extend([f"- `{name}`" for name in status["failed_names"]])
    return "\n".join(lines) + "\n"
