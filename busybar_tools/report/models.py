from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass
class ReportOptions:
    device: str
    cli_port: int
    http_port: int = 80
    output: Optional[str] = None
    api_token: Optional[str] = None
    timeout: int = 5
    include_logs: bool = True
    include_screens: bool = True
    include_cli: bool = True


@dataclass
class ReportManifest:
    created_at: str
    tool: str = "busybar-tools"
    tool_version: str = "unknown"
    device: dict = field(default_factory=dict)
    host: dict = field(default_factory=dict)
    collectors: List[dict] = field(default_factory=list)

    def ok(self, name: str, output: str, detail: Optional[str] = None):
        item = {"name": name, "status": "ok", "output": output}
        if detail:
            item["detail"] = detail
        self.collectors.append(item)

    def skipped(self, name: str, reason: str):
        self.collectors.append({"name": name, "status": "skipped", "reason": reason})

    def failed(self, name: str, error: Union[Exception, str]):
        self.collectors.append({"name": name, "status": "failed", "error": str(error)})
