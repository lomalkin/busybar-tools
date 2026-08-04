from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile


def default_output_path() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return str(Path.cwd() / f"busybar-report-{stamp}.zip")


def json_bytes(data) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def write_json(zipf: ZipFile, path: str, data) -> None:
    zipf.writestr(path, json_bytes(data))
