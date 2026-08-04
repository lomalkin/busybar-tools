from __future__ import annotations

import os
import platform
import socket
import sys
from datetime import datetime
from importlib.metadata import version
from zipfile import ZIP_DEFLATED, ZipFile

from busybar_tools.api import BusybarApiClient
from busybar_tools.report.cli import collect_cli
from busybar_tools.report.http import collect_json_endpoints
from busybar_tools.report.logs import collect_logs
from busybar_tools.report.models import ReportManifest, ReportOptions
from busybar_tools.report.screens import collect_screens
from busybar_tools.report.summary import build_summary, summary_markdown
from busybar_tools.report.util import default_output_path, write_json


def _tool_version() -> str:
    try:
        return version("busybar-tools")
    except Exception:
        return "unknown"


def create_report(options: ReportOptions) -> str:
    output = options.output or default_output_path()
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)

    api = BusybarApiClient(
        options.endpoint.host,
        port=options.http_port,
        token=options.api_token,
        timeout=options.timeout,
    )
    manifest = ReportManifest(
        created_at=datetime.now().isoformat(timespec="seconds"),
        tool_version=_tool_version(),
        device={
            "host": options.endpoint.host,
            "http_port": options.http_port,
            "cli_port": options.endpoint.port,
        },
        host={
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
    )
    collected = {}

    with ZipFile(output, "w", ZIP_DEFLATED) as zipf:
        collect_json_endpoints(zipf, api, manifest, collected)
        if options.include_screens:
            collect_screens(zipf, api, manifest, collected)
        else:
            manifest.skipped("screens", "disabled")
        if options.include_logs:
            collect_logs(zipf, api, manifest, collected)
        else:
            manifest.skipped("logs", "disabled")
        if options.include_cli:
            collect_cli(zipf, options, manifest, collected)
        else:
            manifest.skipped("cli", "disabled")

        summary = build_summary(options, manifest, collected)
        write_json(zipf, "summary.json", summary)
        zipf.writestr("SUMMARY.md", summary_markdown(summary))
        write_json(zipf, "manifest.json", manifest.__dict__)

    return output


__all__ = ["ReportManifest", "ReportOptions", "create_report"]
