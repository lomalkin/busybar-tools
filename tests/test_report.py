import base64
import json
import zipfile

import busybar_tools.report as report
import busybar_tools.report.cli as report_cli
from busybar_tools.report import ReportOptions, create_report


class FakeApi:
    fail_logs = False

    def __init__(self, host, port=80, token=None, timeout=5):
        self.deleted = []

    def get_json(self, path, params=None):
        if path == "/api/version":
            return {"api_semver": "1.2.3", "token": "secret-token"}
        if path == "/api/name":
            return {"name": "Desk Bar"}
        if path == "/api/transport":
            return {"type": "usb"}
        if path == "/api/status/device":
            return {"serial_number": "secret-serial", "usb_mac": "aa:bb:cc:dd:ee:ff"}
        if path == "/api/access":
            return {"mode": "disabled", "key_valid": False}
        if path == "/api/storage/status":
            return {"used_bytes": 10, "free_bytes": 20, "total_bytes": 30}
        return {"path": path, "params": params or {}}

    def get_bytes(self, path, params=None):
        if path == "/api/screen":
            display = (params or {}).get("display", 0)
            raw = b"\x00\x20\x40" * (72 * 16) if display == 0 else b"\x0f" * (160 * 80 // 2)
            return base64.b64encode(raw)
        if path == "/api/storage/read":
            return b"[I][Boot] Ready\n[W][Net] Link is unstable\n[E][Update] Download failed ssid=Office\n"
        return b"{}"

    def post_bytes(self, path, params=None, data=b""):
        if path == "/api/log_dump" and self.fail_logs:
            raise RuntimeError("no log endpoint")
        return b'{"result":"ok"}'

    def delete_bytes(self, path, params=None):
        self.deleted.append((path, params))
        return b'{"result":"ok"}'


class FakeBsb:
    def __init__(self, address):
        self.address = address
        self.in_sl_cli = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cmd_oneshot(self, command, timeout=1):
        if command == "device_info":
            return [
                "u5_firmware_target: 21",
                "u5_usb_mac: aa:bb:cc:dd:ee:ff",
                "u5_hardware_uid: 00112233445566778899aabb",
                "u5_firmware_branch: release",
                "u5_firmware_commit: abc123",
                "u5_firmware_builddate: 2026-07-10",
                "sl_firmware_branch: release",
                "sl_firmware_commit: def456",
                "sl_firmware_builddate: 2026-07-10",
            ]
        if command == "top 0":
            return [
                "Threads: 3, ISR Time: 0.00%, Uptime: 1h2m3s",
                "Heap: total 1000, free 500, minimum 400, max block 300",
            ]
        if command == "free":
            return ["Heap: total 1000, free 500, minimum 400, max block 300"]
        if command == "?":
            return ["device_info", "free", "top"]
        return [f"{command}: ok"]

    def cmd_sl_cli_enter(self, timeout=5):
        self.in_sl_cli = True
        return ["Welcome to BUSY Bar 917 Command Line Interface!"]

    def cmd_sl_cli_exit(self, timeout=2):
        self.in_sl_cli = False
        return []

    def cmd_interrupt(self, timeout=2):
        return []


def test_report_collects_logs_and_manifest(monkeypatch, tmp_path):
    FakeApi.fail_logs = False
    monkeypatch.setattr(report, "BusybarApiClient", FakeApi)
    monkeypatch.setattr(report_cli, "BSB_Lite", FakeBsb)

    out = tmp_path / "report.zip"
    path = create_report(ReportOptions(device="192.0.2.1", cli_port=23, output=str(out)))

    assert path == str(out)
    with zipfile.ZipFile(out) as zipf:
        assert b"ssid=<redacted>" in zipf.read("logs/dump.log")
        assert b"[E][Update] Download failed" in zipf.read("logs/errors.txt")
        assert b"[W][Net] Link is unstable" in zipf.read("logs/warnings.txt")
        assert zipf.read("screens/front.png").startswith(b"\x89PNG\r\n\x1a\n")
        assert zipf.read("screens/back.png").startswith(b"\x89PNG\r\n\x1a\n")
        assert b"Heap:" in zipf.read("cli/free.txt")
        assert b"device_info" in zipf.read("cli/help.txt")
        assert b"Threads:" in zipf.read("cli/top_u5.txt")
        assert b"Threads:" in zipf.read("cli/top_917.txt")
        assert b"secret-token" not in zipf.read("api/version.json")
        assert b"secret-serial" in zipf.read("api/status_device.json")
        assert b"aa:bb:cc:dd:ee:ff" not in zipf.read("api/status_device.json")
        assert b"key_valid" in zipf.read("api/access.json")
        assert b"<redacted>" not in zipf.read("api/access.json")
        device_info = zipf.read("cli/device_info.txt").decode()
        assert "u5_firmware_commit" in device_info
        assert "u5_hardware_uid: 00112233445566778899aabb" in device_info
        assert "u5_usb_mac: <redacted>" in device_info
        summary_md = zipf.read("SUMMARY.md")
        assert summary_md.startswith(b"# BUSY Bar Report")
        assert b"Errors found in logs" in summary_md
        assert b"errors_path=logs/errors.txt" in summary_md
        assert b"last_errors" not in summary_md
        summary = json.loads(zipf.read("summary.json"))
        manifest = json.loads(zipf.read("manifest.json"))
    assert summary["device"]["name"] == "Desk Bar"
    assert summary["device"]["target"] == "21"
    assert summary["firmware"]["device_info"]["u5_commit"] == "abc123"
    assert summary["artifacts"]["runtime"]["u5_top"] == "cli/top_u5.txt"
    assert summary["artifacts"]["runtime"]["si917_top"] == "cli/top_917.txt"
    assert summary["artifacts"]["runtime"]["free"] == "cli/free.txt"
    assert summary["tool"]["name"] == "busybar-tools"
    assert summary["findings"][0]["severity"] == "error"
    assert any(item["name"] == "logs:dump" and item["status"] == "ok" for item in manifest["collectors"])


def test_report_skips_logs_when_endpoint_is_missing(monkeypatch, tmp_path):
    FakeApi.fail_logs = True
    monkeypatch.setattr(report, "BusybarApiClient", FakeApi)
    monkeypatch.setattr(report_cli, "BSB_Lite", FakeBsb)

    out = tmp_path / "report.zip"
    create_report(ReportOptions(device="192.0.2.1", cli_port=23, output=str(out)))

    with zipfile.ZipFile(out) as zipf:
        names = set(zipf.namelist())
        assert "SUMMARY.md" in names
        assert "summary.json" in names
        manifest = json.loads(zipf.read("manifest.json"))
    assert "logs/dump.log" not in names
    assert any(item["name"] == "logs:dump" and item["status"] == "failed" for item in manifest["collectors"])
