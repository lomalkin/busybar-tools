from __future__ import annotations

from typing import Any, Dict
from zipfile import ZipFile

from busybar_tools.bsb_lite import BSB_Lite
from busybar_tools.report.models import ReportManifest, ReportOptions
from busybar_tools.report.redaction import redact_lines


CLI_COMMANDS = [
    ("help", "?", 5),
    ("device_info", "device_info", 3),
    ("free", "free", 3),
    ("top_u5", "top 0", 5),
    ("date", "date", 2),
    ("timezone", "timezone", 2),
    ("power_info", "power info", 3),
    ("power_pd_info", "power pd_info", 3),
    ("netstat", "netstat", 3),
    ("fontstat", "fontstat", 3),
    ("light_sensor", "light_sensor", 3),
    ("log_help", "log ?", 2),
]


def collect_cli(
    zipf: ZipFile,
    options: ReportOptions,
    manifest: ReportManifest,
    collected: Dict[str, Any],
) -> None:
    cli_results = {}
    try:
        with BSB_Lite((options.device, options.cli_port)) as bsb:
            for slug, command, timeout in CLI_COMMANDS:
                name = f"cli:{command}"
                try:
                    lines = redact_lines(bsb.cmd_oneshot(command, timeout=timeout))
                    archive_path = f"cli/{slug}.txt"
                    zipf.writestr(archive_path, "\n".join(lines) + "\n")
                    cli_results[slug] = {"command": command, "lines": lines, "path": archive_path}
                    manifest.ok(name, archive_path)
                except Exception as exc:
                    manifest.failed(name, exc)
            collect_917_top(zipf, bsb, manifest, cli_results)
    except Exception as exc:
        manifest.failed("cli:connect", exc)
    if cli_results:
        collected["cli"] = cli_results


def collect_917_top(
    zipf: ZipFile,
    bsb: BSB_Lite,
    manifest: ReportManifest,
    cli_results: Dict[str, Any],
) -> None:
    name = "cli:917 top"
    entered = False
    try:
        enter_lines = redact_lines(bsb.cmd_sl_cli_enter(timeout=8))
        enter_text = "\n".join(enter_lines)
        if "Welcome to BUSY Bar 917" not in enter_text and "917 Command Line Interface" not in enter_text:
            bsb.CLI_PROMPT = bsb.CLI_PROMPT_DEFAULT
            raise RuntimeError("Could not enter 917 CLI")
        entered = True
        if enter_lines:
            zipf.writestr("cli/sl_cli_enter.txt", "\n".join(enter_lines) + "\n")
            cli_results["sl_cli_enter"] = {
                "command": "sl_cli",
                "lines": enter_lines,
                "path": "cli/sl_cli_enter.txt",
            }
        lines = redact_lines(bsb.cmd_oneshot("top 0", timeout=5))
        archive_path = "cli/top_917.txt"
        zipf.writestr(archive_path, "\n".join(lines) + "\n")
        cli_results["top_917"] = {"command": "sl_cli -> top 0", "lines": lines, "path": archive_path}
        manifest.ok(name, archive_path)
    except Exception as exc:
        manifest.failed(name, exc)
    finally:
        if entered:
            try:
                bsb.cmd_interrupt(timeout=1)
            except Exception:
                pass
            try:
                bsb.cmd_sl_cli_exit(timeout=3)
            except Exception as exc:
                manifest.failed("cli:917 exit", exc)
